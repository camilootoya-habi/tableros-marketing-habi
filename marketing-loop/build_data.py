#!/usr/bin/env python3
"""Ensambla marketing-loop/data.json para el tablero Marketing Loop.
Fuentes: BigQuery (comparativa, funnel, creación, ciclo) + hojas públicas (respuestas, envíos base) + Infobip (calidad línea).
Uso: python3 build_data.py   (corre desde la carpeta del tablero; requiere bq autenticado).
Infobip opcional: env INFOBIP_BASE_URL + INFOBIP_MX_API_KEY + INFOBIP_CO_API_KEY."""
import json, os, csv, io, subprocess, datetime, re, sys, calendar

HERE = os.path.dirname(os.path.abspath(__file__))
def q(name):
    sql = open(os.path.join(HERE, name)).read()
    out = subprocess.run(["bq","query","--use_legacy_sql=false","--format=json","--max_rows=100000"],
        input=sql, capture_output=True, text=True, timeout=600)
    try: return json.loads(out.stdout)
    except Exception as e: print(f"WARN bq {name}: {e}\n{out.stdout[:300]}\n{out.stderr[:300]}"); return []

def sheet(url):
    raw = subprocess.run(["curl","-sL",url], capture_output=True, text=True, timeout=60).stdout
    return list(csv.DictReader(io.StringIO(raw)))

def n10(v):
    d = re.sub(r"[^0-9]","", v or ""); return d[-10:] if len(d)>=10 else None

# --- hojas ---
SS_RESP = "1gQGgBQHW5cUxMMc_N4IR6ylBkCmb-klITKbfL44AEsQ"
SS_ENV  = "1Jh7sIwv8Dkf-2VmW6wIfUSYexRmSu3iR_lZP7JUzD74"
RESP_GID = {"MX":["1470880789","1526041046"],"CO":["158300647"]}   # respuestas por LÍNEA: MX vieja + nueva
def resp_rows(pais):
    out=[]
    for gid in RESP_GID[pais]: out += sheet(csv_url(SS_RESP, gid))
    return out
ENV_GID  = {"MX":"241433433","CO":"1571565293"}
def csv_url(ss,gid): return f"https://docs.google.com/spreadsheets/d/{ss}/export?format=csv&gid={gid}"

# --- serie diaria: envíos (repo privado) + respuestas/interesados (hoja) ---
GH_TOKEN = os.environ.get("GH_READ_TOKEN")
PRIV_REPO = "camilootoya-habi/marketing-loop-lead-nurturing"
SENT_PATH = {"MX":"backbone-mx-batch/infobip_sent_history_mx.csv","CO":"backbone-mx-batch/infobip_sent_history_co.csv"}
def fetch_private_csv(path):
    if not GH_TOKEN: print("  ⚠ sin GH_READ_TOKEN, no leo envíos privados"); return []
    out=subprocess.run(["curl","-s","-H",f"Authorization: token {GH_TOKEN}","-H","Accept: application/vnd.github.raw",
        f"https://api.github.com/repos/{PRIV_REPO}/contents/{path}"],capture_output=True,text=True,timeout=60).stdout
    return list(csv.DictReader(io.StringIO(out)))
def fetch_private_json(path):
    if not GH_TOKEN: print("  ⚠ sin GH_READ_TOKEN, no leo geo_health"); return None
    out=subprocess.run(["curl","-s","-H",f"Authorization: token {GH_TOKEN}","-H","Accept: application/vnd.github.raw",
        f"https://api.github.com/repos/{PRIV_REPO}/contents/{path}"],capture_output=True,text=True,timeout=60).stdout
    try: return json.loads(out)
    except: return None
def norm_date(s):
    s=(s or "").strip()
    m=re.match(r"(\d{4})-(\d{2})-(\d{2})",s)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m=re.match(r"(\d{2})-(\d{2})-(\d{4})",s)   # DD-MM-YYYY
    if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None
def diario(pais, crea=None):
    env={}
    for r in fetch_private_csv(SENT_PATH[pais]):
        if "hatsapp" in (r.get("canal") or "").lower():
            d=norm_date(r.get("fecha_envio"))
            if d: env[d]=env.get(d,0)+1
    resp={}; inter={}; yv={}; pb={}
    for r in resp_rows(pais):
        d=None
        for k,v in r.items():
            if k and "Fecha" in k and v: d=norm_date(v); break
        if not d: continue
        resp[d]=resp.get(d,0)+1
        et=(r.get("ETAPA") or "").upper()
        if "INTERESADO" in et: inter[d]=inter.get(d,0)+1
        elif "YA VENDIO" in et: yv[d]=yv.get(d,0)+1
        elif "PIDE BAJA" in et: pb[d]=pb.get(d,0)+1
    cre={}; cal={}
    for r in (crea or []):
        if r.get("pais")==pais:
            d=norm_date(r.get("fecha"))
            if d: cre[d]=int(r.get("creados") or 0); cal[d]=int(r.get("calificados") or 0)
    dias=sorted(set(env)|set(resp)|set(inter)|set(cre))
    return [{"fecha":d,"enviados":env.get(d,0),"respuestas":resp.get(d,0),"interesados":inter.get(d,0),
             "ya_vendio":yv.get(d,0),"pide_baja":pb.get(d,0),
             "creados":cre.get(d,0),"calificados":cal.get(d,0)} for d in dias]

def respuestas(pais):
    rows = resp_rows(pais)
    hoy = datetime.date.today()
    ini = hoy - datetime.timedelta(days=14)   # ventana: últimos 14 días completos, sin incluir hoy: [hoy-14, hoy-1]
    def fdate(r):
        for k,v in r.items():
            if k and "Fecha" in k and v:
                m = re.search(r"(\d{4})-(\d{2})-(\d{2})", v)
                if m:
                    try: return datetime.date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
                    except: return None
        return None
    c = {"INTERESADO":0,"YA VENDIO":0,"PIDE BAJA":0}
    for r in rows:
        d = fdate(r)
        if not d or d < ini or d >= hoy: continue   # excluye hoy y >14 días
        et = (r.get("ETAPA") or "").strip().upper()
        if et in c: c[et]+=1
    total = sum(c.values())
    return {"interesado":c["INTERESADO"], "ya_vendio":c["YA VENDIO"], "pide_baja":c["PIDE BAJA"], "total_respuestas":total, "ventana":"14d"}

def base_enviada(pais):
    # hoja de envíos: primeras filas metadata, luego teléfonos por columna
    raw = subprocess.run(["curl","-sL",csv_url(SS_ENV, ENV_GID[pais])], capture_output=True, text=True, timeout=60).stdout
    rows = list(csv.reader(io.StringIO(raw)))
    tel=set()
    for r in rows[2:]:
        for cell in r:
            t=n10(cell)
            if t: tel.add(t)
    return len(tel)

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

# --- Meta (WhatsApp Business Management API) — fuente autoritativa de salud + salida real ---
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

def meta_analytics(pais, days=14):
    """{YYYY-MM-DD: {enviados, entregados}} por día (Meta), filtrado a nuestra línea. Meta cuenta en UTC."""
    end   = datetime.datetime.utcnow().replace(hour=0,minute=0,second=0,microsecond=0)+datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=days+2)
    s,e = calendar.timegm(start.timetuple()), calendar.timegm(end.timetuple())
    phones = ",".join(f"'{p}'" for p in MART_LINES.get(pais, [SENDER[pais]]))   # AMBAS líneas MX (vieja+nueva)
    d = graph(WABA[pais], {"fields":f"analytics.start({s}).end({e}).granularity(DAY).phone_numbers([{phones}])"})
    out={}
    for p in ((((d or {}).get("analytics") or {}).get("data_points")) or []):
        day=datetime.datetime.utcfromtimestamp(p["start"]).strftime("%Y-%m-%d")
        out[day]={"enviados":p.get("sent",0),"entregados":p.get("delivered",0)}
    return out

def salida(pais, diario_rows, days=7):
    """Embudo de SALIDA real: encolados (Infobip 200) → enviados (Meta) → entregados (Meta) → respondieron.
    Ventana: últimos `days` días COMPLETOS (excluye hoy, día parcial). Todo en el mismo rango."""
    an = meta_analytics(pais, days)
    hoy = datetime.date.today(); ini = hoy - datetime.timedelta(days=days)
    enc = {r["fecha"]: r.get("enviados",0) for r in diario_rows}   # 'enviados' del diario = lo que ENCOLAMOS
    serie=[]; tenc=tsent=tdel=0
    for d in sorted(set(enc)|set(an)):
        try: dd=datetime.date(*map(int,d.split("-")))
        except: continue
        if dd<ini or dd>=hoy: continue
        e=enc.get(d,0); m=an.get(d,{}); s=m.get("enviados",0); de=m.get("entregados",0)
        serie.append({"fecha":d,"encolados":e,"enviados":s,"entregados":de}); tenc+=e; tsent+=s; tdel+=de
    # respondieron en la MISMA ventana de 7d completos (excluye hoy)
    resp=0
    for r in resp_rows(pais):
        for k,v in r.items():
            if k and "Fecha" in k and v:
                m=re.search(r"(\d{4})-(\d{2})-(\d{2})",v)
                if m:
                    try: dd=datetime.date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
                    except: dd=None
                    if dd and ini<=dd<hoy: resp+=1
                break
    return {"serie":serie, "ventana":f"{days}d",
            "totales":{"encolados":tenc,"enviados":tsent,"entregados":tdel,"respondieron":resp},
            "tasa_salida":  round(tsent/tenc,3) if tenc else None,   # Meta sacó / encolamos
            "tasa_entrega": round(tdel/tsent,3) if tsent else None,  # entregados / enviados
            "respond_rate": round(resp/tdel,3) if tdel else None}    # respuestas / entregados (denominador CORRECTO)

def by_pais(rows, key="pais"):
    out={}
    for r in rows: out.setdefault(r.get(key), []).append(r)
    return out

# --- funnel por cosecha (atribuido al último envío) / por fecha de evento ---
LEDGER_PATHS = {
  "MX": ["backbone-mx-batch/decoy_mx_ledger.csv","backbone-mx-batch/backbone-leads-mx-ledger.csv","backbone-mx-batch/mapping_confianza.csv"],
  "CO": ["backbone-mx-batch/backbone-leads-co-ledger.csv","backbone-mx-batch/decoy_co_ledger.csv"],
}
def bucket(dstr, tipo):
    try: y,m,dd = map(int, dstr.split("-"))
    except: return None
    dt=datetime.date(y,m,dd)
    if tipo=="dia": return dstr
    if tipo=="mes": return f"{y:04d}-{m:02d}-01"
    if tipo=="semana": return (dt-datetime.timedelta(days=dt.weekday())).isoformat()          # lunes
    if tipo=="ciclo":  return (dt-datetime.timedelta(days=(dt.weekday()-2)%7)).isoformat()     # miércoles
def funnel_tables(pais, recre):
    sends={}; deliv=[]
    for r in fetch_private_csv(SENT_PATH[pais]):
        if "hatsapp" not in (r.get("canal") or "").lower(): continue
        d=norm_date(r.get("fecha_envio")); ph=r.get("telefono_10")
        if d and ph:
            sends.setdefault(ph,[]).append(d)
            if (r.get("estado_entrega") or "").strip().lower()=="entregado": deliv.append(d)   # entregados por fecha de envío
    for ph in sends: sends[ph].sort()
    def last_send(ph,before):
        L=sends.get(ph);  prev=[x for x in (L or []) if x<=before]
        return prev[-1] if prev else (L[0] if L else None)
    # respuestas: (telefono, nid_original, fecha, etapa)
    resp=[]
    for r in resp_rows(pais):
        d=None
        for k,v in r.items():
            if k and "Fecha" in k and v: d=norm_date(v); break
        ph=n10(r.get("Telefono")); nid=(r.get("NID") or "").strip()
        if d and ph: resp.append((ph,nid,d,(r.get("ETAPA") or "").upper()))
    # info del lead recreado, indexada por nid nuevo y por deal_id (=id_negocio). El deal_id cubre los decoy (sin new_nid).
    info_nid={}; info_deal={}
    for r in recre:
        if r.get("pais")!=pais: continue
        rec=(r.get("fecha_creacion"), int(r.get("calif") or 0))
        if r.get("nid"): info_nid[str(r["nid"])]=rec
        if r.get("deal_id"): info_deal[str(r["deal_id"])]=rec
    # ledger: old_nid -> (fecha_recreacion, calificó). Enlaza por new_nid o, si es decoy (sin nid), por deal_id.
    old2rec={}
    for path in LEDGER_PATHS[pais]:
        for r in fetch_private_csv(path):
            on=(r.get("old_nid") or "").strip()
            if not on: continue
            nn=(r.get("new_nid") or r.get("decoy_nid") or "").strip()
            did=(r.get("new_deal_id") or r.get("decoy_deal_id") or "").strip()
            info=info_nid.get(nn) or info_deal.get(did)
            ts=(r.get("timestamp") or "")[:10]
            fecha=(info[0] if info else None) or (ts or None)
            calif=info[1] if info else 0
            old2rec[on]=(fecha,calif)
    out={"cosecha":{},"evento":{}}
    for tipo in ("dia","ciclo","semana","mes"):
        C={}; E={}
        def add(D,b,k):
            if not b: return
            D.setdefault(b,{"enviados":0,"entregados":0,"respondieron":0,"interesados":0,"creados":0,"calificados":0})[k]+=1
        for ph,dates in sends.items():
            for d in dates:
                b=bucket(d,tipo); add(E,b,"enviados"); add(C,b,"enviados")
        for d in deliv:   # entregados (estado reconciliado) por fecha de envío, en ambas vistas
            b=bucket(d,tipo); add(E,b,"entregados"); add(C,b,"entregados")
        # creados/calificados se anclan al INTERESADO (recreamos el 100%): creados = interesados recreados.
        # cosecha → cohorte del envío que originó la respuesta; evento → fecha real de recreación.
        for ph,nid,d,et in resp:
            be=bucket(d,tipo); cs=last_send(ph,d); bc=bucket(cs,tipo) if cs else None
            add(E,be,"respondieron"); add(C,bc,"respondieron")
            if "INTERESADO" not in et: continue
            add(E,be,"interesados"); add(C,bc,"interesados")
            rec=old2rec.get(nid)
            if not rec: continue
            fecha,cal=rec
            add(C,bc,"creados")
            if cal: add(C,bc,"calificados")
            add(E,bucket(fecha,tipo),"creados")
            if cal: add(E,bucket(fecha,tipo),"calificados")
        out["cosecha"][tipo]=[{"bucket":b,**v} for b,v in sorted(C.items())]
        out["evento"][tipo]=[{"bucket":b,**v} for b,v in sorted(E.items())]
    return out

def antifunnel(pais, recre):
    """Distribución por ESTADO ACTUAL del backbone de los leads recreados, bucketeada por fecha_creacion
    en cada granularidad (dia/ciclo/semana/mes). Salida: {series:{tipo:[{bucket,estados:{label:n}}]}, meta:{label:{estado_id,calif}}}."""
    rows=[r for r in recre if r.get("pais")==pais and r.get("fecha_creacion")]
    series={}
    for tipo in ("dia","ciclo","semana","mes"):
        agg={}
        for r in rows:
            b=bucket(r.get("fecha_creacion"), tipo)
            if not b: continue
            lab=(r.get("estado_label") or "Sin estado")
            agg.setdefault(b,{})
            agg[b][lab]=agg[b].get(lab,0)+1
        series[tipo]=[{"bucket":b,"estados":est} for b,est in sorted(agg.items())]
    meta={}
    for r in rows:
        lab=(r.get("estado_label") or "Sin estado")
        if lab not in meta:
            meta[lab]={"estado_id":r.get("estado_id"),"calif":int(r.get("calif") or 0)}
    return {"series":series,"meta":meta}

def cohorte_origen(pais):
    """Respond rate y % interesados por TRIMESTRE de fecha de creación del LEAD ORIGINAL.
    Solo cubre los envíos 'auto' (los que capturaron nid + fecha_creacion_original); une envíos↔respuestas por nid.
    Salida: [{bucket:'YYYY-QN', enviados, respondieron, interesados}] ordenado."""
    resp=set(); inter=set()
    for r in resp_rows(pais):
        nid=(r.get("NID") or "").strip()
        if not (nid and nid.isdigit()): continue
        resp.add(nid)
        if "INTERESADO" in (r.get("ETAPA") or "").upper(): inter.add(nid)
    seen={}   # dedup por nid original
    for r in fetch_private_csv(SENT_PATH[pais]):
        nid=(r.get("nid") or "").strip(); fco=norm_date(r.get("fecha_creacion_original"))
        if nid and fco and nid not in seen: seen[nid]=fco
    agg={}
    for nid,fco in seen.items():
        try: y,m=fco[:4], int(fco[5:7])
        except: continue
        b=f"{y}-Q{(m-1)//3+1}"
        a=agg.setdefault(b,{"bucket":b,"enviados":0,"respondieron":0,"interesados":0})
        a["enviados"]+=1
        if nid in resp: a["respondieron"]+=1
        if nid in inter: a["interesados"]+=1
    return [agg[k] for k in sorted(agg)]

COMP_FIELDS=["direccion","telefono","email","nombre","geo","zona","tipo","area","banos",
             "medios_banos","habitaciones","garaje","ascensor","piso","antiguedad","precio","estrato"]
def completitud(pais, rows):
    """Completitud de datos de los leads creados: por período, total creados + cuántos tienen cada campo poblado.
    Salida: {series:{tipo:[{bucket,total,<campo>:have}]}, na:[campos no aplicables al país]}."""
    sub=[r for r in rows if r.get("pais")==pais]
    na=[f for f in COMP_FIELDS if sub and all((r.get("c_"+f) in (None,"","None")) for r in sub)]
    series={}
    for t in ("dia","ciclo","semana","mes"):
        agg={}
        for r in sub:
            b=bucket(r.get("fecha_creacion"), t)
            if not b: continue
            a=agg.setdefault(b, {"bucket":b,"total":0})
            a["total"]+=1
            for f in COMP_FIELDS:
                if str(r.get("c_"+f))=="1": a[f]=a.get(f,0)+1
        series[t]=[agg[k] for k in sorted(agg)]
    return {"series":series,"na":na}

def bq_sql(sql):
    """Corre SQL inline en BigQuery y devuelve filas (JSON). [] si falla (ej. sin acceso al mart CO)."""
    out = subprocess.run(["bq","query","--use_legacy_sql=false","--format=json","--max_rows=100000"],
                         input=sql, capture_output=True, text=True, timeout=600)
    try: return json.loads(out.stdout)
    except Exception as e: print(f"  ⚠ bq_sql: {e}"); return []

MART_LINES = {"MX":["5215590883423","5215595483481"], "CO":["573009110453"]}
NEW_LINE   = {"MX":"5215595483481", "CO":"573009110453"}
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

def por_hora(pais):
    """READ RATE y RESPOND RATE por HORA de envío (hora real del mart de Infobip), sobre TODOS
    nuestros envíos entregados. read = seen_at/entregados · respond = (entregados cuyo tel respondió)
    /entregados. NO usamos delivery rate por hora (estaba contaminado por la línea quemada); read y
    respond son comportamiento del destinatario, más limpios. CO sin acceso al mart → vacío."""
    lines = ",".join(f'"{l}"' for l in MART_LINES.get(pais, []))
    if pais != "MX" or not lines:
        return {"serie":[], "nota":"pendiente acceso al mart de CO"}
    rows = bq_sql(f'''SELECT EXTRACT(HOUR FROM {SENDAT}) hora,
        RIGHT(REGEXP_REPLACE(to_number, r"[^0-9]", ""),10) tel10,
        LOWER(TRIM(status)) status, IF({SEEN},1,0) seen
      FROM `{mart_table(pais)}`
      WHERE TRIM(from_number) IN ({lines}) AND DATE({SENDAT}) >= "2026-06-01"''')
    responders = {n10(r.get("Telefono")) for r in resp_rows(pais)}; responders.discard(None)
    agg={}
    for r in rows:
        h=r.get("hora")
        if h in (None,""): continue
        h=int(h); a=agg.setdefault(h,{"env":0,"e":0,"l":0,"r":0})
        a["env"]+=1                                   # volumen total salido esa hora
        if r.get("status")=="delivered":
            a["e"]+=1
            if str(r.get("seen"))=="1": a["l"]+=1
            if r.get("tel10") in responders: a["r"]+=1
    serie=[{"hora":h, "enviados":agg[h]["env"], "entregados":agg[h]["e"],
            "read_rate":   round(agg[h]["l"]/agg[h]["e"],3) if agg[h]["e"] else None,
            "respond_rate":round(agg[h]["r"]/agg[h]["e"],3) if agg[h]["e"] else None} for h in sorted(agg)]
    return {"serie":serie, "desde":"2026-06-01",
            "nota":"read/respond rate por hora de envío (hora del mart, TZ a calibrar); respond = entregados cuyo tel respondió"}

CREA = q("query_creacion.sql")
RECRE = q("query_recreados.sql")
COMP = q("query_completitud.sql")
RESP_D  = {p: respuestas(p) for p in ("MX","CO")}
DIARIO  = {p: diario(p, CREA) for p in ("MX","CO")}
data = {
  "updated": os.environ.get("BUILD_TS") or datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),  # fecha de descarga vía query (corrida del cron)
  "comparativa": q("query_comparativa.sql"),
  "funnel": q("query_funnel.sql"),
  "creacion": CREA,
  "ciclo": q("query_ciclo.sql"),
  "respuestas": RESP_D,
  "base_enviada": {p: base_enviada(p) for p in ("MX","CO")},
  "diario": DIARIO,
  "funnel_tabla": {p: funnel_tables(p, RECRE) for p in ("MX","CO")},
  "antifunnel": {p: antifunnel(p, RECRE) for p in ("MX","CO")},
  "completitud": {p: completitud(p, COMP) for p in ("MX","CO")},
  "cohorte_origen": {p: cohorte_origen(p) for p in ("MX","CO")},
  "hoy": {r["pais"]: int(r.get("creados_hoy") or 0) for r in q("query_hoy.sql")},
  "geo_health": fetch_private_json("backbone-mx-batch/geo_health.json"),
  "address_health": fetch_private_json("backbone-mx-batch/address_health.json"),
  "linea": {p: linea_meta(p) for p in ("MX","CO")},                       # calidad/estado/review/throughput DE META
  "salida": {p: salida(p, DIARIO[p]) for p in ("MX","CO")},               # embudo real 7d completos: encolado→enviado→entregado→respondió
  "read": {p: read_stats(p) for p in ("MX","CO")},                        # read rate (seen_at) nivel línea, 14d
  "por_hora": {p: por_hora(p) for p in ("MX","CO")},                      # read/respond rate por hora de envío (mart)
}
open(os.path.join(HERE,"data.json"),"w").write(json.dumps(data, ensure_ascii=False, separators=(",",":")))
print("data.json OK |",
      "comparativa",len(data["comparativa"]),
      "| funnel",len(data["funnel"]),
      "| creacion",len(data["creacion"]),
      "| ciclo",len(data["ciclo"]),
      "| resp MX",data["respuestas"]["MX"], "| base MX",data["base_enviada"]["MX"],
      "| linea MX",data["linea"]["MX"])
