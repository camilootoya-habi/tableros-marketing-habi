#!/usr/bin/env python3
"""Ensambla marketing-loop/data.json para el tablero Marketing Loop.
Fuentes: Neon (send_log/recreation/contact_status vía sources_neon) + mart de Infobip en BigQuery
(sources_mart: outbound/inbound/nid→trimestre/estado actual) + Meta Graph API (salud de línea,
con fallback a Infobip Senders API) + BigQuery (completitud, creados hoy).
Uso: python3 build_data.py   (corre desde la carpeta del tablero; requiere NEON_DATABASE_URL,
bq autenticado y opcionalmente META_ACCESS_TOKEN / INFOBIP_*_API_KEY como respaldo)."""
import json, os, subprocess, datetime, re
import agg, sources_neon as N, sources_mart as M

HERE = os.path.dirname(os.path.abspath(__file__))

def q(name):
    sql = open(os.path.join(HERE, name)).read()
    out = subprocess.run(["bq","query","--use_legacy_sql=false","--format=json","--max_rows=100000"],
        input=sql, capture_output=True, text=True, timeout=600)
    try: return json.loads(out.stdout)
    except Exception as e: print(f"WARN bq {name}: {e}\n{out.stdout[:300]}\n{out.stderr[:300]}"); return []

def n10(v):
    d = re.sub(r"[^0-9]","", v or ""); return d[-10:] if len(d)>=10 else None

# --- Infobip Senders API (respaldo de linea_meta cuando Meta no responde o no trae tier) ---
def linea(pais, sender):
    base=os.environ.get("INFOBIP_BASE_URL","https://xrwqpl.api.infobip.com")
    key=os.environ.get(f"INFOBIP_{pais}_API_KEY")
    if not key: return None
    try:
        out=subprocess.run(["curl","-s",f"{base}/whatsapp/2/senders?limit=200",
            "--header",f"Authorization: App {key}","--header","Accept: application/json"],
            capture_output=True,text=True,timeout=30).stdout
        d=json.loads(out); res=d.get("results") or d
        for s in res:
            if s.get("sender")==sender:
                return {"sender":sender,"quality":s.get("qualityRating"),"tier":s.get("limit"),"status":s.get("connectionStatus")}
    except Exception as e: print(f"WARN infobip {pais}: {e}")
    return None

# --- Meta (WhatsApp Business Management API) — fuente autoritativa de salud de línea ---
META_TOKEN = os.environ.get("META_ACCESS_TOKEN")
GRAPH  = "https://graph.facebook.com/v21.0"
WABA   = {"MX":"1364183988959673","CO":"3861160544193112"}
SENDER = {"MX":"5215595483481","CO":"573009110453"}   # MX: línea NUEVA HIGH (la vieja 5215590883423 en reposo)
def graph(path, params):
    if not META_TOKEN: return None
    args=["curl","-s","-G",f"{GRAPH}/{path}"]
    for k,v in params.items(): args+=["--data-urlencode",f"{k}={v}"]
    args+=["--data-urlencode",f"access_token={META_TOKEN}"]
    try: return json.loads(subprocess.run(args,capture_output=True,text=True,timeout=45).stdout)
    except Exception as e: print(f"WARN graph {path}: {e}"); return None

def linea_meta(pais):
    """Salud de línea DIRECTO de Meta (más fiel que Infobip; CO salía UNKNOWN en Infobip y es MEDIUM en Meta).
    tier suele venir vacío por Graph → se completa con Infobip como respaldo."""
    waba, sender = WABA[pais], SENDER[pais]
    ph  = graph(f"{waba}/phone_numbers", {"fields":"display_phone_number,quality_rating,messaging_limit_tier,status,throughput","limit":50})
    inf = graph(waba, {"fields":"account_review_status"})
    out = {"sender":sender,"quality":None,"tier":None,"status":None,
           "review":(inf or {}).get("account_review_status"),"throughput":None,"source":"meta"}
    QMAP={"GREEN":"HIGH","YELLOW":"MEDIUM","RED":"LOW","UNKNOWN":"UNKNOWN"}   # vocab Meta → el que ya usa el tablero
    for p in ((ph or {}).get("data") or []):
        if n10(p.get("display_phone_number"))==n10(sender):
            out["quality"]=QMAP.get(p.get("quality_rating"), p.get("quality_rating"))
            out["tier"]=p.get("messaging_limit_tier")
            out["status"]=p.get("status"); out["throughput"]=(p.get("throughput") or {}).get("level")
    if out["quality"] is None:          # Meta no respondió → cae a Infobip completo
        return linea(pais, sender) or out
    if not out["tier"]:                 # tier vacío por Graph → respaldo Infobip
        ib=linea(pais, sender)
        if ib: out["tier"]=ib.get("tier"); out["tier_source"]="infobip"
    return out

def bq_sql(sql):
    """Corre SQL inline en BigQuery y devuelve filas (JSON). [] si falla (ej. sin acceso al mart CO)."""
    out = subprocess.run(["bq","query","--use_legacy_sql=false","--format=json","--max_rows=100000"],
                         input=sql, capture_output=True, text=True, timeout=600)
    try: return json.loads(out.stdout)
    except Exception as e: print(f"  ⚠ bq_sql: {e}"); return []

MART_LINES = {"MX":["5215590883423","5215595483481"], "CO":["573009110453"]}
def mart_table(pais): return f"papyrus-master.infobib_gold_{pais.lower()}.mart_infobip_messages_daily_{pais.lower()}"
SEEN = 'TRIM(seen_at) NOT IN ("","-") AND seen_at IS NOT NULL'
SENDAT = 'SAFE.PARSE_DATETIME("%d/%m/%Y %H:%M:%S", TRIM(send_at_raw))'

def read_stats(pais, days=14):
    """Read rate (nivel línea) desde el mart: leídos (seen_at) / entregados, últimos `days` días.
    CO sin acceso al mart → None (se muestra 'pendiente')."""
    lines = ",".join(f'"{l}"' for l in MART_LINES.get(pais, []))
    if not lines: return None
    rows = bq_sql(f'''SELECT COUNTIF(LOWER(TRIM(status))="delivered") entregados,
        COUNTIF(LOWER(TRIM(status))="delivered" AND {SEEN}) leidos
      FROM `{mart_table(pais)}`
      WHERE TRIM(from_number) IN ({lines}) AND DATE({SENDAT}) >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)''')
    if not rows: return None
    e=int(rows[0].get("entregados") or 0); l=int(rows[0].get("leidos") or 0)
    return {"entregados":e, "leidos":l, "read_rate": round(l/e,3) if e else None, "ventana":f"{days}d"}

def por_hora(pais, inbound_phones=None):
    """READ RATE y RESPOND RATE por HORA de envío (hora real del mart de Infobip), sobre TODOS
    nuestros envíos entregados. read = seen_at/entregados · respond = (entregados cuyo tel respondió)
    /entregados. NO usamos delivery rate por hora (estaba contaminado por la línea quemada); read y
    respond son comportamiento del destinatario, más limpios. CO sin acceso al mart → vacío.
    `inbound_phones`: set de teléfonos (10 dígitos) que respondieron (de sources_mart.inbound_rows);
    si no se pasa, se calcula aquí (últimos 30d) para no depender de las hojas viejas."""
    lines = ",".join(f'"{l}"' for l in MART_LINES.get(pais, []))
    if pais != "MX" or not lines:
        return {"serie":[], "nota":"pendiente acceso al mart de CO"}
    rows = bq_sql(f'''SELECT EXTRACT(HOUR FROM {SENDAT}) hora,
        RIGHT(REGEXP_REPLACE(to_number, r"[^0-9]", ""),10) tel10,
        LOWER(TRIM(status)) status, IF({SEEN},1,0) seen
      FROM `{mart_table(pais)}`
      WHERE TRIM(from_number) IN ({lines}) AND DATE({SENDAT}) >= "2026-06-01"''')
    responders = inbound_phones if inbound_phones is not None else {i["phone"] for i in M.inbound_rows(30) if i.get("phone")}
    agg_h={}
    for r in rows:
        h=r.get("hora")
        if h in (None,""): continue
        h=int(h); a=agg_h.setdefault(h,{"env":0,"e":0,"l":0,"r":0})
        a["env"]+=1                                   # volumen total salido esa hora
        if r.get("status")=="delivered":
            a["e"]+=1
            if str(r.get("seen"))=="1": a["l"]+=1
            if r.get("tel10") in responders: a["r"]+=1
    serie=[{"hora":h, "enviados":agg_h[h]["env"], "entregados":agg_h[h]["e"],
            "read_rate":   round(agg_h[h]["l"]/agg_h[h]["e"],3) if agg_h[h]["e"] else None,
            "respond_rate":round(agg_h[h]["r"]/agg_h[h]["e"],3) if agg_h[h]["e"] else None} for h in sorted(agg_h)]
    return {"serie":serie, "desde":"2026-06-01",
            "nota":"read/respond rate por hora de envío (hora del mart, TZ a calibrar); respond = entregados cuyo tel respondió"}

COMP_FIELDS=["direccion","telefono","email","nombre","geo","zona","tipo","area","banos",
             "medios_banos","habitaciones","garaje","ascensor","piso","antiguedad","precio","estrato"]
def completitud(pais, rows):
    """Completitud de datos de los leads creados: por período, total creados + cuántos tienen cada campo poblado.
    Salida: {series:{tipo:[{bucket,total,<campo>:have}]}, na:[campos no aplicables al país]}."""
    sub=[r for r in rows if r.get("pais")==pais]
    na=[f for f in COMP_FIELDS if sub and all((r.get("c_"+f) in (None,"","None")) for r in sub)]
    series={}
    for t in ("dia","ciclo","semana","mes"):
        buckets={}
        for r in sub:
            b=agg.bucket(r.get("fecha_creacion"), t)
            if not b: continue
            a=buckets.setdefault(b, {"bucket":b,"total":0})
            a["total"]+=1
            for f in COMP_FIELDS:
                if str(r.get("c_"+f))=="1": a[f]=a.get(f,0)+1
        series[t]=[buckets[k] for k in sorted(buckets)]
    return {"series":series,"na":na}

# --- helpers nuevos: respuestas parseadas del mart (INTERESADO/YAVENDIO/OTRO) y A/B por template ---
def _resp_tipos(parsed, mbm, win, sl7):
    """Cuenta INTERESADO/YAVENDIO/OTRO entre los inbound parseados (mart) en la ventana de `win` días
    completos (excluye hoy). respond_rate = respuestas (en la ventana) / entregados EN LA MISMA VENTANA
    (`sl7`, envíos de los últimos `win` días), no sobre todo `mbm` (~30d) — evita subestimar la tasa."""
    hoy = datetime.date.today()
    ini = (hoy - datetime.timedelta(days=win)).isoformat()
    fin = hoy.isoformat()
    c = {"INTERESADO":0, "YAVENDIO":0, "OTRO":0}
    for _phone, pr, ts in parsed:
        if not (ini <= (ts or "") < fin): continue
        act = pr.get("action") or "OTRO"
        c[act] = c.get(act,0) + 1
    total = sum(c.values())
    entregados = sum(1 for r in sl7 if (mbm.get(r.get("message_id") or "") or {}).get("status")=="delivered")
    return {"interesado":c["INTERESADO"], "ya_vendio":c["YAVENDIO"], "otro":c["OTRO"],
            "total_respuestas":total, "ventana":f"{win}d",
            "respond_rate": round(total/entregados,3) if entregados else None}

def _ab(sl, mbm, inbound_phones):
    """Comparativo A/B por `template` de send_log: enviados, entregados (vía mbm), delivery_rate,
    respondieron (teléfono en inbound_phones), respond_rate (sobre entregados, igual que agg.embudo)."""
    from collections import defaultdict
    A=defaultdict(lambda: dict(enviados=0,entregados=0,respondieron=0))
    for r in sl:
        t = r.get("template") or "sin_template"
        a = A[t]; a["enviados"]+=1
        m = mbm.get(r.get("message_id") or "")
        if m and m.get("status")=="delivered": a["entregados"]+=1
        if r.get("phone") in inbound_phones: a["respondieron"]+=1
    out=[]
    for t in sorted(A):
        a=A[t]
        out.append({"template":t, "enviados":a["enviados"], "entregados":a["entregados"],
            "delivery_rate": round(a["entregados"]/a["enviados"],3) if a["enviados"] else None,
            "respondieron":a["respondieron"],
            "respond_rate": round(a["respondieron"]/a["entregados"],3) if a["entregados"] else None})
    return out

# --- ensamblado ---
COMP = q("query_completitud.sql")
WIN = 7
sl = N.send_log_rows()                        # todos (para cohorte histórica)
hoy = datetime.date.today()
hoy7 = (hoy - datetime.timedelta(days=WIN)).isoformat()
hoy_iso = hoy.isoformat()
sl7 = [r for r in sl if hoy7 <= (r.get("attempted_at") or "")[:10] < hoy_iso]   # 7d completos, excluye hoy
rec = N.recreation_rows(); cst = N.contact_status_rows()
mbm = M.mart_by_msgid(30)
import sources_infobip as I
ibm = I.delivery_by_msgid([r.get("message_id") for r in sl if r.get("message_id")])
mbm = {**mbm, **ibm}   # Infobip (tiempo real) pisa el mart en los recientes; el mart cubre el histórico
inb = M.inbound_rows(30)
# respuestas parseadas del mart
parsed=[(i["phone"], agg.parse_resp(i["respuesta_cliente"]), i["ts"]) for i in inb]
inbound_phones={p for p,_,_ in parsed if p}
interesado_phones={p for p,pr,_ in parsed if p and pr["action"]=="INTERESADO"}
# recreados/calificados por old_nid
recreated_oldnids={r["old_nid"] for r in rec if r.get("success")}
qualified_oldnids={r["old_nid"] for r in rec if r.get("state_at_creation") in (20,63)}
dias=[(hoy-datetime.timedelta(days=k)).isoformat() for k in range(WIN,0,-1)]
# cohorte necesita nid->trimestre
nidq=M.nid2quarter(list({r["nid"] for r in sl if r.get("nid")}))
# antifunnel: estado actual de recreados
est=M.estado_actual_by_deal([r["new_deal_id"] for r in rec if r.get("new_deal_id")])
for r in rec: r["estado_actual"]=est.get(str(r.get("new_deal_id")))

data={
  "updated": os.environ.get("BUILD_TS") or datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
  "linea": {"MX": linea_meta("MX"), "CO": None},
  "embudo": {"MX": agg.embudo(sl7,mbm,inbound_phones,interesado_phones,recreated_oldnids,qualified_oldnids,dias), "CO": None},
  "errores": {"MX": agg.errores_por_tipo(sl7,mbm), "CO": None},
  "respuestas": {"MX": _resp_tipos(parsed, mbm, WIN, sl7), "CO": None},
  "cohorte": {"MX": agg.cohorte(sl,mbm,nidq), "CO": None},
  "ab_templates": {"MX": _ab(sl,mbm,inbound_phones), "CO": None},
  "recreacion": {"MX": {t: agg.recreacion_serie(rec,t) for t in ("dia","semana","mes")}, "CO": None},
  "antifunnel": {"MX": {t: agg.antifunnel_serie(rec,t) for t in ("dia","semana","mes")}, "CO": None},
  "contact_status": {"MX": agg.contact_dist(cst), "CO": None},
  "por_hora": {"MX": por_hora("MX", inbound_phones), "CO": {"serie":[]}},
  "completitud": {p: completitud(p, COMP) for p in ("MX","CO")},
  "hoy": {r["pais"]: int(r.get("creados_hoy") or 0) for r in q("query_hoy.sql")},
}
open(os.path.join(HERE,"data.json"),"w").write(json.dumps(data, ensure_ascii=False, separators=(",",":")))
print("data.json OK |",
      "send_log",len(sl), "(7d)",len(sl7),
      "| recreation",len(rec), "| contact_status",len(cst),
      "| mart_msgids",len(mbm), "| infobip",len(ibm), "| inbound",len(inb),
      "| linea MX",data["linea"]["MX"],
      "| embudo tasas",data["embudo"]["MX"]["tasas"],
      "| errores",data["errores"]["MX"],
      "| respuestas",data["respuestas"]["MX"])
