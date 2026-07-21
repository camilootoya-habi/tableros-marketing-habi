#!/usr/bin/env python3
"""Ensambla marketing-loop/data.json para el tablero Marketing Loop.
Fuentes: Neon (send_log/recreation/contact_status vía sources_neon) + mart de Infobip en BigQuery
(sources_mart: outbound/inbound/nid→trimestre/estado actual) + Meta Graph API (salud de línea,
con fallback a Infobip Senders API) + BigQuery (completitud, creados hoy).
Uso: python3 build_data.py   (corre desde la carpeta del tablero; requiere NEON_DATABASE_URL,
bq autenticado y opcionalmente META_ACCESS_TOKEN / INFOBIP_*_API_KEY como respaldo)."""
import json, os, subprocess, datetime, re
import agg, sources_neon as N, sources_mart as M, sources_infobip as I

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
      WHERE TRIM(from_number) IN ({lines}) AND DATE({SENDAT}) >= "2026-06-01"
        -- SOLO envíos de CAMPAÑA (con plantilla). Excluye mensajes de sesión/conversación (template NULL):
        -- esos son respuestas del bot dentro de conversaciones activas -> van a quien ya respondió, inflando
        -- el respond rate a ~100% en horas de bajo volumen (00-09). No son el blast de reactivación.
        AND NULLIF(TRIM(template), "") IS NOT NULL''')
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
    # Siempre las 24 horas (0-23), aunque no haya envíos esa hora (enviados=0, rate=None) -> se ve el día completo.
    serie=[]
    for h in range(24):
        a=agg_h.get(h, {"env":0,"e":0,"l":0,"r":0})
        serie.append({"hora":h, "enviados":a["env"], "entregados":a["e"],
            "read_rate":   round(a["l"]/a["e"],3) if a["e"] else None,
            "respond_rate":round(a["r"]/a["e"],3) if a["e"] else None})
    return {"serie":serie, "desde":"2026-06-01",
            "nota":"read/respond rate por hora de envío de CAMPAÑA (con plantilla; excluye mensajes de sesión); hora CDMX (UTC-6, verificado vs Neon); respond = entregados cuyo tel respondió"}

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
def _ab(sl, mbm, inbound_phones, interesado_phones, yavendio_phones, keyfield="template"):
    """Comparativo por `keyfield` (template o fuente): enviados, entregados, delivery/read/respond/interesado/optout rate.
    delivery = entregados/enviados; read/respond/interesado/optout = x/entregados. Excluye fallidos por bug 7008.
    optout = tocaron el botón «Ya no vendo» (YAVENDIÓ) — interacción NEGATIVA medible por plantilla."""
    from collections import defaultdict
    A=defaultdict(lambda: dict(enviados=0,entregados=0,leidos=0,respondieron=0,interesados=0,yavendio=0))
    for r in sl:
        m = mbm.get(r.get("message_id") or "")
        if m and "7008" in (m.get("error_name") or ""): continue  # bug plantilla sin imagen (7008): fuera de la comparación
        t = r.get(keyfield) or "(sin dato)"
        a = A[t]; a["enviados"]+=1
        if m and m.get("status")=="delivered":
            a["entregados"]+=1
            if m.get("seen"): a["leidos"]+=1
        if r.get("phone") in inbound_phones: a["respondieron"]+=1
        if r.get("phone") in interesado_phones: a["interesados"]+=1
        if r.get("phone") in yavendio_phones: a["yavendio"]+=1
    def rate(x,y): return round(x/y,3) if y else None
    out=[]
    for t in sorted(A):
        a=A[t]
        out.append({keyfield:t, "enviados":a["enviados"], "entregados":a["entregados"],
            "delivery_rate": rate(a["entregados"],a["enviados"]),
            "leidos":a["leidos"], "read_rate": rate(a["leidos"],a["entregados"]),
            "respondieron":a["respondieron"], "respond_rate": rate(a["respondieron"],a["entregados"]),
            "interesados":a["interesados"], "interesado_rate": rate(a["interesados"],a["entregados"]),
            "yavendio":a["yavendio"], "optout_rate": rate(a["yavendio"],a["entregados"])})
    return out

# Inicio del experimento A/B (config.EXPERIMENT.since MX / countries.co CO)
AB_SINCE = {"MX": "2026-07-16", "CO": "2026-07-17"}
def _ab_veredicto(rows, since):
    """Veredicto bayesiano del A/B sobre INTERESADO rate (interesados/entregados), v1 control vs v2 oferta.
    Misma metodología/umbrales que el motor (ab_stats.decide)."""
    import ab_stats
    ctrl = next((r for r in rows if "_v1_" in (r.get("template") or "")), None)
    ofer = next((r for r in rows if "_v2_" in (r.get("template") or "")), None)
    if not ctrl or not ofer or not ctrl["entregados"] or not ofer["entregados"]:
        return {"disponible": False}
    dias = (datetime.date.today() - datetime.date.fromisoformat(since)).days + 1
    d = ab_stats.decide(ctrl["template"], ctrl["entregados"], ctrl["interesados"],
                        ofer["template"], ofer["entregados"], ofer["interesados"], dias)
    return {"disponible": True, "ganador": ("v2" if d["winner"]==ofer["template"] else "v1"),
            "prob": round(d["prob_winner"],3), "loss_pp": round(d["expected_loss_winner"]*100,3),
            "decidido": d["decided"], "razon": d["reason"], "dias": dias,
            "entregados": {"v1": ctrl["entregados"], "v2": ofer["entregados"]},
            "min_brazo": 300, "min_dias": 7}

# --- ensamblado ---
WIN = 7

def build_country(pais):
    """Calcula TODOS los valores country-specific para `pais` (MX o CO): send_log/recreation/contact_status
    de Neon filtrados por país (tz local del país), delivery = mart del país ∪ Infobip /logs del país,
    inbound del país, y las series derivadas (embudo/errores/respuestas/cosecha/ab/recreacion/antifunnel/
    contact_status/cohorte_origen/diario/por_hora/linea). Devuelve un dict con esas claves."""
    sl = N.send_log_rows(country=pais)                 # todos (para cohorte histórica)
    hoy = datetime.date.today()
    win_start = (hoy - datetime.timedelta(days=WIN-1)).isoformat()   # últimos 7d INCLUYENDO hoy
    hoy_iso = hoy.isoformat()
    sl7 = [r for r in sl if win_start <= (r.get("attempted_at") or "")[:10] <= hoy_iso]  # 7d incl hoy (delivery ya es tiempo real vía /logs)
    rec = N.recreation_rows(country=pais); cst = N.contact_status_rows(country=pais)
    mbm = M.mart_by_msgid(30, country=pais)
    # complemento tiempo real (Infobip /logs) SOLO para la ventana reciente; los viejos ya no viven en /logs y el mart los cubre
    ibm = I.delivery_by_msgid([r.get("message_id") for r in sl7 if r.get("message_id")], pais=pais)
    # Infobip (tiempo real) pisa el mart en delivery/error de los recientes; PERO conserva el `seen`
    # del mart (Infobip /logs NO reporta SEEN -> pone seen=False; si lo dejáramos pisar, borraría lecturas reales).
    for mid, v in ibm.items():
        prev = mbm.get(mid)
        mbm[mid] = {**v, "seen": bool((prev or {}).get("seen")) or bool(v.get("seen"))}
    inb = M.inbound_rows(30, country=pais)
    inb_resp = M.inbound_rows(180, country=pais)   # ventana más larga para la tabla de Respuestas por período (día/semana/mes)
    # respuestas parseadas del mart
    parsed=[(i["phone"], agg.parse_resp(i["respuesta_cliente"]), i["ts"]) for i in inb]
    inbound_phones={p for p,_,_ in parsed if p}
    interesado_phones={p for p,pr,_ in parsed if p and pr["action"]=="INTERESADO"}
    yavendio_phones={p for p,pr,_ in parsed if p and pr["action"]=="YAVENDIO"}   # opt-out por botón «Ya no vendo»
    # --- REPO VIEJO: envíos de la plantilla vieja (jun–jul) que solo viven en el mart, para la Cosecha ---
    old_sl, old_mbm = M.old_repo_sends(pais)
    for mid, v in old_mbm.items(): mbm.setdefault(mid, v)   # completa delivery/seen de los viejos (no pisa los recientes/​/logs)
    sl_cosecha = old_sl + sl                                # Cosecha = histórico completo (viejo mart + nuevo Neon)
    # respuestas atribuibles a envíos viejos: ventana amplia (180d) parseada
    parsed_wide=[(i["phone"], agg.parse_resp(i["respuesta_cliente"]), i["ts"]) for i in inb_resp]
    inbound_phones_wide={p for p,_,_ in parsed_wide if p}
    interesado_phones_wide={p for p,pr,_ in parsed_wide if p and pr["action"]=="INTERESADO"}
    # INTERESADOS PENDIENTES POR CREAR: respondieron INTERESADO (nid del payload) pero su nid aún NO está en
    # la tabla recreation (no se recreó el lead). Fuente de verdad = mart inbound. Card + fila de la Cosecha.
    recreated_nids={str(r["old_nid"]) for r in rec if r.get("old_nid")}
    interesado_pairs=[(p, pr.get("nid")) for p,pr,_ in parsed_wide if p and pr["action"]=="INTERESADO" and pr.get("nid")]
    pend_nids={nid for _,nid in interesado_pairs if nid not in recreated_nids}
    pendientes_crear=len(pend_nids)
    interesado_nocreado_phones={p for p,nid in interesado_pairs if nid not in recreated_nids}
    # recreados/calificados por old_nid
    recreated_oldnids={r["old_nid"] for r in rec if r.get("success")}
    qualified_oldnids={r["old_nid"] for r in rec if r.get("state_at_creation") in (20,63)}
    dias=[(hoy-datetime.timedelta(days=k)).isoformat() for k in range(WIN-1,-1,-1)]  # hoy-6..hoy (incl hoy)
    # cohorte por antigüedad del lead original: nid->trimestre de creación (envíos NUEVOS con nid en send_log)
    nidq=M.nid2quarter(list({r["nid"] for r in sl if r.get("nid")}), country=pais)
    for r in sl: r["quarter"]=nidq.get(r.get("nid"))   # trimestre del lead original por nid — SOLO mensajes nuevos (log de Neon)
    # nid->fuente del lead original (para la tabla "Comparación por fuente", análoga al A/B)
    nidf=M.nid2fuente(list({r["nid"] for r in sl if r.get("nid")}), country=pais)
    for r in sl: r["fuente_lead"]=nidf.get(r.get("nid"), "(sin fuente)")
    # Recreación + Antifunnel: desde tablas internas (query_recreados.sql = hubspot deals UTM reinteresados
    # → TIG → estado REAL del backbone + catálogo de nombres). Reemplaza la tabla `recreation` de Neon, que
    # nunca capturó new_deal_id/state_at_creation (dejaba ambas secciones vacías). Trae viejo + nuevo por UTM.
    recreados=[r for r in RECRE if r.get("pais")==pais]
    return {
        "linea": linea_meta(pais),
        "embudo": agg.embudo(sl7,mbm,inbound_phones,interesado_phones,recreated_oldnids,qualified_oldnids,dias),
        "errores": {t: agg.errores_serie(sl_cosecha, mbm, t, n=40) for t in ("dia","semana","mes")},
        "respuestas": {t: agg.respuestas_serie(inb_resp, t) for t in ("dia","semana","mes")},
        "cosecha": {t: agg.cosecha_serie(sl_cosecha, mbm, inbound_phones_wide, interesado_phones_wide, interesado_nocreado_phones, t, n=40) for t in ("dia","semana","mes")},
        "pendientes_crear": pendientes_crear,
        "ab_templates": _ab(sl,mbm,inbound_phones,interesado_phones,yavendio_phones),
        "ab_fuentes": _ab(sl,mbm,inbound_phones,interesado_phones,yavendio_phones,keyfield="fuente_lead"),
        "antifunnel": {t: agg.antifunnel_serie(recreados,t) for t in ("dia","semana","mes")},
        "contact_status": agg.contact_dist(cst),
        "por_hora": por_hora(pais, inbound_phones),
        "cohorte_origen": agg.cohorte_origen_serie(sl, inbound_phones, interesado_phones),
        "diario": agg.diario_serie(sl_cosecha, inb_resp, rec),
        "_debug": {"send_log":len(sl), "sl7":len(sl7), "recreation":len(rec), "contact_status":len(cst),
                   "mart_msgids":len(mbm), "infobip":len(ibm), "inbound":len(inb)},
    }

COMP = q("query_completitud.sql")
RECRE = q("query_recreados.sql")   # recreados (UTM reinteresados) con estado real del backbone → Recreación + Antifunnel
mx = build_country("MX")
co = build_country("CO")

data={
  "updated": os.environ.get("BUILD_TS") or datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
  "linea": {"MX": mx["linea"], "CO": co["linea"]},
  "embudo": {"MX": mx["embudo"], "CO": co["embudo"]},
  "errores": {"MX": mx["errores"], "CO": co["errores"]},
  "respuestas": {"MX": mx["respuestas"], "CO": co["respuestas"]},
  "cosecha": {"MX": mx["cosecha"], "CO": co["cosecha"]},
  "ab_templates": {"MX": mx["ab_templates"], "CO": co["ab_templates"]},
  "ab_fuentes": {"MX": mx["ab_fuentes"], "CO": co["ab_fuentes"]},
  "ab_veredicto": {"MX": _ab_veredicto(mx["ab_templates"], AB_SINCE["MX"]),
                   "CO": _ab_veredicto(co["ab_templates"], AB_SINCE["CO"])},
  "antifunnel": {"MX": mx["antifunnel"], "CO": co["antifunnel"]},
  "contact_status": {"MX": mx["contact_status"], "CO": co["contact_status"]},
  "por_hora": {"MX": mx["por_hora"], "CO": co["por_hora"]},
  "completitud": {p: completitud(p, COMP) for p in ("MX","CO")},
  "hoy": {r["pais"]: int(r.get("creados_hoy") or 0) for r in q("query_hoy.sql")},
  "comparativa": q("query_comparativa.sql"),
  "pendientes_crear": {"MX": mx["pendientes_crear"], "CO": co["pendientes_crear"]},
  # Muestra (últimos 5, todas las columnas) de cada tabla de Neon — hojas 'Tablas' (explicación)
  "neon_tablas": {p: {t: N.tabla_muestra(t, oc, country=p)
                      for t,oc in (("send_log","attempted_at"),("recreation","created_at"),("contact_status","updated_at"))}
                  for p in ("MX","CO")},
  "cohorte_origen": {"MX": mx["cohorte_origen"], "CO": co["cohorte_origen"]},
  "diario": {"MX": mx["diario"], "CO": co["diario"]},
  "asignados": q("query_asignados.sql"),
}
open(os.path.join(HERE,"data.json"),"w").write(json.dumps(data, ensure_ascii=False, separators=(",",":")))
print("data.json OK |",
      "MX send_log",mx["_debug"]["send_log"], "(7d)",mx["_debug"]["sl7"],
      "| recreation",mx["_debug"]["recreation"], "| contact_status",mx["_debug"]["contact_status"],
      "| mart_msgids",mx["_debug"]["mart_msgids"], "| infobip",mx["_debug"]["infobip"], "| inbound",mx["_debug"]["inbound"])
print("data.json OK |",
      "CO send_log",co["_debug"]["send_log"], "(7d)",co["_debug"]["sl7"],
      "| recreation",co["_debug"]["recreation"], "| contact_status",co["_debug"]["contact_status"],
      "| mart_msgids",co["_debug"]["mart_msgids"], "| infobip",co["_debug"]["infobip"], "| inbound",co["_debug"]["inbound"])
print("| linea MX",data["linea"]["MX"], "| linea CO",data["linea"]["CO"])
print("| embudo tasas MX",data["embudo"]["MX"]["tasas"], "| embudo tasas CO",data["embudo"]["CO"]["tasas"])
print("| errores MX",data["errores"]["MX"], "| errores CO",data["errores"]["CO"])
print("| respuestas MX",data["respuestas"]["MX"], "| respuestas CO",data["respuestas"]["CO"])
