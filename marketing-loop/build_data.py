#!/usr/bin/env python3
"""Ensambla marketing-loop/data.json para el tablero Marketing Loop.
Fuentes: Neon (send_log/recreation/contact_status vía sources_neon) + mart de Infobip en BigQuery
(sources_mart: outbound/inbound/nid→trimestre/estado actual) + Meta Graph API (salud de línea,
con fallback a Infobip Senders API) + BigQuery (completitud, creados hoy).
Uso: python3 build_data.py   (corre desde la carpeta del tablero; requiere NEON_DATABASE_URL,
bq autenticado y opcionalmente META_ACCESS_TOKEN / INFOBIP_*_API_KEY como respaldo)."""
import json, os, subprocess, datetime, re
import agg, sources_neon as N, sources_mart as M, sources_infobip as I

def _SNC():
    """Conexión cruda a la misma base del tablero (para queries con CTEs y FILTER)."""
    import psycopg
    return psycopg.connect(N._db_url())

HERE = os.path.dirname(os.path.abspath(__file__))

# Proyecto que FACTURA los jobs de BQ (las tablas se leen cross-project). No se hereda del
# `gcloud config` del runner a propósito: el proyecto ambiente son los papyrus-*, que ya no
# aceptan bigquery.jobs.create y dejaban todas las secciones de BQ en vacío sin fallar el cron.
BQ_PROJECT = os.environ.get("BQ_BILLING_PROJECT", "sellers-main-prod")

# Plantilla ganadora vigente por pais (A/B tpl_v1_vs_v2_jul26, cerrado 2026-07-22): la serie
# "mejor hora" se calcula SOLO sobre esta plantilla para no mezclar efectos de plantilla y hora.
WINNER_TPL = {"MX": "reactivacion_sellers_mx_v2_oferta_jul26",
              "CO": "reactivacion_sellers_co_v2_oferta_jul26"}
BQ_CMD = ["bq", f"--project_id={BQ_PROJECT}", "query",
          "--use_legacy_sql=false", "--format=json", "--max_rows=100000"]

def q(name):
    sql = open(os.path.join(HERE, name)).read()
    out = subprocess.run(BQ_CMD,
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
    out = subprocess.run(BQ_CMD,
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
    if not lines:
        return {"serie":[], "nota":f"sin líneas configuradas para {pais}"}
    # El mart guarda send_at en hora LOCAL de cada país (MX=CDMX UTC-6, CO=Bogotá UTC-5;
    # ambos verificados message_id↔Neon) → EXTRACT(HOUR) ya devuelve la hora local, sin ajuste.
    rows = bq_sql(f'''SELECT EXTRACT(HOUR FROM {SENDAT}) hora,
        RIGHT(REGEXP_REPLACE(to_number, r"[^0-9]", ""),10) tel10,
        LOWER(TRIM(status)) status, IF({SEEN},1,0) seen
      FROM `{mart_table(pais)}`
      WHERE TRIM(from_number) IN ({lines}) AND DATE({SENDAT}) >= "2026-06-01"
        -- SOLO la plantilla GANADORA vigente (v2 oferta). Antes: cualquier plantilla de campaña, pero el
        -- mix v1/v2 contamina la señal por hora (entrega/lectura difieren por plantilla). Los mensajes de
        -- sesión (template NULL) siguen excluidos: van a quien ya respondió e inflan el respond rate.
        AND TRIM(template) = "{WINNER_TPL[pais]}"''')
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
    tzlab = {"MX":"hora CDMX (UTC-6)", "CO":"hora Bogotá (UTC-5)"}.get(pais, "hora local")
    return {"serie":serie, "desde":"2026-06-01",
            "nota":f"delivery/open/response rate por hora de envío, SOLO plantilla ganadora v2 ({WINNER_TPL[pais]}); excluye mensajes de sesión; {tzlab}, verificado vs Neon; response = entregados cuyo tel respondió. Horas con muestra chica (<30 env / <20 entregados) no dibujan tasa"}

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


# --- A/B de POOL: segmento "comité + lead >=2025" vs aleatorio (pool_comite25_vs_random_ago26) ---
# Diseño: marketing-loop-sellers/docs/superpowers/specs/2026-07-30-ab-pool-comite-design.md
# Brazo derivado del NID contra TIG (regla de asignación == membresía): sin columnas nuevas en Neon.
POOL_AB = {"since": "2026-07-30", "fc_min": "2025-01-01", "min_brazo": 300, "min_dias": 7, "max_dias": 21}

def _pool_ab(pais):
    import math, ab_stats
    import sources_neon as _SN, sources_mart as _SM
    rows = _SN._rows(
        """SELECT sl.nid::text AS nid, sl.delivery_status, cs.state
           FROM send_log sl LEFT JOIN contact_status cs ON cs.phone=sl.phone AND cs.country=sl.country
           WHERE sl.country=%s AND sl.nid IS NOT NULL
             AND (sl.attempted_at AT TIME ZONE %s)::date >= %s""",
        (pais, _SN.TZ[pais], POOL_AB["since"]))
    if not rows: return {"disponible": False}
    nids = sorted({r["nid"] for r in rows if (r["nid"] or "").isdigit()})
    arm = {}
    for i in range(0, len(nids), 40000):
        inl = ",".join(nids[i:i+40000])
        for x in _SM._bq(f"""SELECT CAST(nid AS STRING) nid,
              IF(fecha_comite IS NOT NULL AND CAST(fecha_creacion AS DATE)>=\"{POOL_AB['fc_min']}\",
                 'segmento','control') arm
            FROM `{_SM.TIG[pais]}` WHERE nid IN ({inl})
            QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY fecha_creacion DESC)=1"""):
            arm[x["nid"]] = x["arm"]
    agg = {"segmento": {"enviados":0,"entregados":0,"interesados":0},
           "control":  {"enviados":0,"entregados":0,"interesados":0}}
    for r in rows:
        a = agg.get(arm.get(r["nid"] or ""))
        if a is None: continue
        a["enviados"] += 1
        if (r.get("delivery_status") or "").lower() == "delivered": a["entregados"] += 1
        if r.get("state") == "reinteresado": a["interesados"] += 1
    s, c = agg["segmento"], agg["control"]
    if not s["entregados"] or not c["entregados"]: return {"disponible": False}
    dias = (datetime.date.today() - datetime.date.fromisoformat(POOL_AB["since"])).days + 1
    d = ab_stats.decide("control", c["entregados"], c["interesados"],
                        "segmento", s["entregados"], s["interesados"], dias)
    for a in (s, c):
        a["pos_rate"] = round(a["interesados"]/a["entregados"], 4) if a["entregados"] else None
        a["delivery_rate"] = round(a["entregados"]/a["enviados"], 4) if a["enviados"] else None
    min_del = min(s["entregados"], c["entregados"])
    ritmo = max(min_del/dias, 1e-9)
    eta = max(math.ceil(max(0, POOL_AB["min_brazo"]-min_del)/ritmo), max(0, POOL_AB["min_dias"]-dias))
    return {"disponible": True, "since": POOL_AB["since"], "dias": dias,
            "brazos": {"segmento": s, "control": c},
            "ganador": d["winner"], "prob": round(d["prob_winner"],3),
            "loss_pp": round(d["expected_loss_winner"]*100,3),
            "decidido": d["decided"], "razon": d["reason"], "eta_dias": (0 if d["decided"] else eta),
            "min_brazo": POOL_AB["min_brazo"], "min_dias": POOL_AB["min_dias"], "max_dias": POOL_AB["max_dias"]}


def _inventario(pais):
    """Serie diaria de inventario del pool por nivel (P1-P4) desde Neon (pool_inventario,
    escrita por el motor). repuesto(d) = stock(d) - stock(d-1) + enviados(d). runway_dias =
    stock actual / consumo promedio 7d del nivel (None si no se consume)."""
    import sources_neon as _SN
    try:
        rows = _SN._rows("""SELECT fecha::text f, tier, stock, enviados FROM pool_inventario
                            WHERE country=%s ORDER BY fecha, tier""", (pais,))
    except Exception:
        return {"disponible": False}
    if not rows: return {"disponible": False}
    from collections import defaultdict
    hist = defaultdict(dict)
    for r in rows: hist[r["tier"]][r["f"]] = {"stock": r["stock"], "enviados": r["enviados"]}
    tiers_out = {}
    for tier, dias in hist.items():
        fechas = sorted(dias)
        serie = []
        prev = None
        for f in fechas:
            d = dias[f]
            rep = None if prev is None else d["stock"] - prev["stock"] + d["enviados"]
            serie.append({"fecha": f, "stock": d["stock"], "enviados": d["enviados"], "repuesto": rep})
            prev = d
        ult = serie[-1]
        env7 = [x["enviados"] for x in serie[-7:] if x["enviados"]]
        consumo = (sum(env7) / len(env7)) if env7 else 0
        tiers_out[tier] = {"serie": serie[-30:], "stock": ult["stock"], "enviados_hoy": ult["enviados"],
                           "repuesto_hoy": ult["repuesto"],
                           "runway_dias": round(ult["stock"] / consumo) if consumo else None}
    return {"disponible": True, "tiers": tiers_out,
            "nota": "P1=comité+2025 · P2=recientes 2025+ · P3=comité viejo · P4=resto. Stock=elegibles tras exclusiones. repuesto=Δstock+enviados."}

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
    # Entrega DURABLE de Neon (persistida por el motor): rellena huecos del mart (p.ej. 22-jul) y pisa
    # con estado terminal, sin regresar terminales frescos ni tocar `seen`. Fuente propia, sin lag.
    nbm = N.delivery_by_msgid(country=pais)
    agg.merge_neon_delivery(mbm, nbm)
    inb = M.inbound_rows(30, country=pais)
    inb_resp = M.inbound_rows(180, country=pais)   # ventana más larga para la tabla de Respuestas por período (día/semana/mes)
    # respuestas parseadas del mart
    parsed=[(i["phone"], agg.parse_resp(i["respuesta_cliente"]), i["ts"]) for i in inb]
    inbound_phones={p for p,_,_ in parsed if p}
    interesado_phones={p for p,pr,_ in parsed if p and pr["action"]=="INTERESADO"}
    yavendio_phones={p for p,pr,_ in parsed if p and pr["action"]=="YAVENDIO"}   # opt-out por botón «Ya no vendo»
    # COMPLEMENTO TIEMPO REAL (2026-08-13): el mart llega con días/semanas de lag y estas filas
    # quedaban en 0 para lo reciente. Neon (contact_status) ya consolida las respuestas del
    # Sheet del bot (tiempo real) + mart + /logs — misma fuente que opera el motor. Se UNE
    # (no pisa): cuando el mart cargue, coincide. El read/seen NO tiene fuente RT (solo mart).
    _neon_resp = N._rows("SELECT phone, state FROM contact_status WHERE country=%s AND responded_at IS NOT NULL", (pais,))
    inbound_phones    |= {r["phone"] for r in _neon_resp}
    interesado_phones |= {r["phone"] for r in _neon_resp if r["state"] == "reinteresado"}
    yavendio_phones   |= {r["phone"] for r in _neon_resp if r["state"] in ("ya_vendio", "baja")}
    # --- REPO VIEJO: envíos de la plantilla vieja (jun–jul) que solo viven en el mart, para la Cosecha ---
    old_sl, old_mbm = M.old_repo_sends(pais)
    for mid, v in old_mbm.items(): mbm.setdefault(mid, v)   # completa delivery/seen de los viejos (no pisa los recientes/​/logs)
    sl_cosecha = old_sl + sl                                # Cosecha = histórico completo (viejo mart + nuevo Neon)
    # respuestas atribuibles a envíos viejos: ventana amplia (180d) parseada
    parsed_wide=[(i["phone"], agg.parse_resp(i["respuesta_cliente"]), i["ts"]) for i in inb_resp]
    inbound_phones_wide={p for p,_,_ in parsed_wide if p}
    interesado_phones_wide={p for p,pr,_ in parsed_wide if p and pr["action"]=="INTERESADO"}
    # COMPLEMENTO TIEMPO REAL (2026-08-13): mismos sets de Neon que arriba — la COSECHA usa
    # estos "_wide" y quedaba en 0 para días recientes con el mart cortado (WhatsApp feed roto 3-ago).
    inbound_phones_wide    |= {r["phone"] for r in _neon_resp}
    interesado_phones_wide |= {r["phone"] for r in _neon_resp if r["state"] == "reinteresado"}
    # INTERESADOS PENDIENTES POR CREAR: respondieron INTERESADO (nid del payload) pero aún NO se recreó el lead.
    # Refinado (2026-07-21) para NO sobre-contar: solo cuenta si además (a) es lead del LOOP (nid en send_log),
    # y (b) NO está en estado TERMINAL (baja/ya_vendio/respondio_otro = se dio de baja o respondió otra cosa).
    # Así excluye opt-outs post-interesado y los interesados del repo viejo que nunca enviamos. Fuente: mart inbound.
    recreated_nids={str(r["old_nid"]) for r in rec if r.get("old_nid")}
    loop_nids={str(r["nid"]) for r in sl if r.get("nid")}                      # (a) leads del loop (en send_log)
    TERMINAL_NEG={"baja","ya_vendio","respondio_otro"}
    terminal_phones={r["phone"] for r in cst if r.get("state") in TERMINAL_NEG}  # (b) estados terminales negativos
    interesado_pairs=[(p, str(pr.get("nid"))) for p,pr,_ in parsed_wide if p and pr["action"]=="INTERESADO" and pr.get("nid")]
    pend=[(p,nid) for p,nid in interesado_pairs
          if nid not in recreated_nids and nid in loop_nids and p not in terminal_phones]
    pendientes_crear=len({nid for _,nid in pend})
    interesado_nocreado_phones={p for p,_ in pend}
    # COSECHA SOLO AGENTE SDR (2026-08-21): mismos números de la cosecha, pero restringidos a los
    # envíos cuyo destinatario terminó conversando con el agente EN VIVO. Se excluyen SHADOW y
    # NOT_IN_SAMPLE a propósito: ahí el agente propone una respuesta pero NO la manda, así que el
    # desenlace de esa conversación no es suyo y mezclarlo inflaría su cosecha con mérito ajeno.
    agente_phones = {r["phone"] for r in N._rows(
        "SELECT DISTINCT phone FROM agent_thread WHERE country=%s AND role='assistant' "
        "AND action_taken IS NOT NULL AND action_taken NOT LIKE 'SHADOW%%' "
        "AND action_taken <> 'NOT_IN_SAMPLE'", (pais,))}
    sl_agente = [r for r in sl_cosecha if r.get("phone") in agente_phones]
    # USUARIOS CONTACTADOS DE VERDAD: teléfonos ÚNICOS con al menos un mensaje ENTREGADO.
    # No son "enviados": un mensaje que rebota (no entregable, bloqueado, freq cap) no contactó
    # a nadie, y contarlo infla la base de todo el funnel. Ventanas acumuladas por fecha de envío.
    _hoy_l = datetime.date.today()
    _desde = {"mtd": _hoy_l.replace(day=1).isoformat(),
              "wtd": (_hoy_l - datetime.timedelta(days=_hoy_l.weekday())).isoformat(),
              "ytd": _hoy_l.replace(month=1, day=1).isoformat()}
    _cont = {k: set() for k in _desde}
    for r in sl_cosecha:
        m = mbm.get(r.get("message_id") or "")
        if not (m and m.get("status") == "delivered"):
            continue
        f = (r.get("attempted_at") or "")[:10]; ph = r.get("phone")
        if not f or not ph:
            continue
        for k, ini in _desde.items():
            if f >= ini:
                _cont[k].add(ph)
    contactados = {k: len(v) for k, v in _cont.items()}
    # ---- PANEL (diseño Habi Loop): embudo por RANGO y por CANAL ----
    # Canal: el loop entra por WEB y ventanas se marca en send_log.campaign. Las filas viejas
    # traen campaign NULL (el sender del loop todavía no la escribe), así que "web" = todo lo
    # que NO es ventanas — que es exactamente lo que significa hoy.
    _rangos = {"hoy": 0, "7": 6, "30": 29, "90": 89}
    def _desde(nd):
        return (_hoy_l - datetime.timedelta(days=nd)).isoformat()
    _canal_de = lambda r: "ventanas" if (r.get("campaign") == "ventanas") else "web"
    panel = {c: {k: {"entregados": 0, "enviados": 0, "reasignados": 0} for k in _rangos}
             for c in ("agregado", "web", "ventanas")}
    for r in sl_cosecha:
        f = (r.get("attempted_at") or "")[:10]
        if not f: continue
        m = mbm.get(r.get("message_id") or "")
        entregado = bool(m and m.get("status") == "delivered")
        cn = _canal_de(r)
        for k, nd in _rangos.items():
            if f >= _desde(nd):
                for dst in (panel[cn][k], panel["agregado"][k]):
                    dst["enviados"] += 1
                    if entregado: dst["entregados"] += 1
    # Leads re-asignados por canal. El loop los crea vía `recreation`; ventanas NO pasa por ahí
    # —su lead lo dispara el agente— así que se cuentan sus BACKBONE en agent_thread. Darlos por
    # 0, como estaba antes, escondía que la campaña ya está generando leads.
    for rr in rec:
        f = str(rr.get("created_at") or "")[:10]
        if not f: continue
        for k, nd in _rangos.items():
            if f >= _desde(nd):
                panel["web"][k]["reasignados"] += 1
                panel["agregado"][k]["reasignados"] += 1
    _vent = N._rows(
        "SELECT (ts AT TIME ZONE %s)::date::text AS f, count(DISTINCT phone) AS n "
        "FROM agent_thread WHERE country=%s AND campaign='ventanas' "
        "  AND action_taken IN ('BACKBONE','BACKBONE_SANITIZED') GROUP BY 1", (N.TZ[pais], pais))
    for r in _vent:
        for k, nd in _rangos.items():
            if r["f"] >= _desde(nd):
                panel["ventanas"][k]["reasignados"] += int(r["n"] or 0)
                panel["agregado"][k]["reasignados"] += int(r["n"] or 0)
    # Serie del loop y del agente por día, para las dos tablas del panel
    _rec_dia = {}
    for rr in rec:
        f = str(rr.get("created_at") or "")[:10]
        if f: _rec_dia[f] = _rec_dia.get(f, 0) + 1
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
        "contactados": contactados,
        "plantillas": plantillas(pais, sl, mbm, interesado_phones, yavendio_phones),
        "panel": panel,
        "reasignados_dia": _rec_dia,
        "cosecha_agente": {t: agg.cosecha_serie(sl_agente, mbm, inbound_phones_wide, interesado_phones_wide, interesado_nocreado_phones, t, n=40) for t in ("dia","semana","mes")},
        "agente_conversaciones": len(agente_phones),
        "ab_templates": _ab(sl,mbm,inbound_phones,interesado_phones,yavendio_phones),
        "ab_fuentes": _ab(sl,mbm,inbound_phones,interesado_phones,yavendio_phones,keyfield="fuente_lead"),
        "antifunnel": {t: agg.antifunnel_serie(recreados,t) for t in ("dia","semana","mes")},
        "contact_status": agg.contact_dist(cst),
        "por_hora": por_hora(pais, inbound_phones),
        "cohorte_origen": agg.cohorte_origen_serie(sl, inbound_phones, interesado_phones),
        "diario": agg.diario_serie(sl_cosecha, inb_resp, rec),
        "_debug": {"send_log":len(sl), "sl7":len(sl7), "recreation":len(rec), "contact_status":len(cst),
                   "mart_msgids":len(mbm), "infobip":len(ibm), "neon_delivery": len(nbm), "inbound":len(inb)},
    }



def plantillas(pais, sl, mbm, interesado_phones, yavendio_phones):
    """Catálogo VIVO de plantillas de la línea + su desempeño real.

    El catálogo sale de Infobip (estado de aprobación de Meta, placeholders, botones, copy);
    el desempeño de nuestro propio send_log cruzado con las respuestas. Se listan solo las
    plantillas CON envíos o las que están en uso: la línea acumula plantillas viejas de otros
    equipos y mostrarlas todas convierte la pantalla en un basurero.
    """
    from collections import defaultdict
    met = defaultdict(lambda: {"enviados": 0, "entregados": 0, "clics": 0, "bajas": 0})
    vistos = defaultdict(set)
    for r in sl:
        tpl = r.get("template")
        if not tpl:
            continue
        m = met[tpl]
        m["enviados"] += 1
        d = mbm.get(r.get("message_id") or "")
        if d and d.get("status") == "delivered":
            m["entregados"] += 1
        ph = r.get("phone")
        if ph and ph not in vistos[tpl]:
            vistos[tpl].add(ph)
            if ph in interesado_phones: m["clics"] += 1
            if ph in yavendio_phones:   m["bajas"] += 1

    base = os.environ.get("INFOBIP_BASE_URL", "https://xrwqpl.api.infobip.com")
    key = os.environ.get(f"INFOBIP_{pais}_API_KEY")
    cat = {}
    if key:
        try:
            import requests as _rq
            r = _rq.get(f"{base}/whatsapp/2/senders/{SENDER[pais]}/templates",
                        headers={"Authorization": f"App {key}", "Accept": "application/json"}, timeout=60)
            if r.status_code == 200:
                for tp in (r.json() or {}).get("templates", []):
                    st = (tp.get("structure") or {})
                    body = (st.get("body") or {})
                    cat[tp.get("name")] = {
                        "estado": tp.get("status"),
                        "idioma": tp.get("language"),
                        "categoria": tp.get("category"),
                        "body": (body.get("text") if isinstance(body, dict) else body) or "",
                        "botones": len((st.get("buttons") or [])),
                    }
            else:
                print(f"WARN plantillas {pais}: Infobip {r.status_code}")
        except Exception as e:
            print(f"WARN plantillas {pais}: {str(e)[:120]}")

    en_uso = set()
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.expanduser("~/habi/marketing-loop-sellers"))
        from countries import get as _get
        c = _get(pais)
        en_uso.add(c.template)
        for v in (getattr(c, "template_experiment", None) or {}).values():
            if isinstance(v, str): en_uso.add(v)
    except Exception:
        pass

    nombres = set(met) | en_uso
    out = []
    for n in sorted(nombres):
        m = met.get(n, {"enviados": 0, "entregados": 0, "clics": 0, "bajas": 0})
        c = cat.get(n, {})
        out.append({"nombre": n, "en_uso": n in en_uso,
                    "estado": c.get("estado") or "(no está en la línea)",
                    "categoria": c.get("categoria"), "botones": c.get("botones"),
                    "body": (c.get("body") or "")[:400], **m})
    out.sort(key=lambda x: (not x["en_uso"], -x["enviados"]))
    return out




def ventanas_ejecuciones(dias=30):
    """Una fila por LEAD con el estado de cada nodo del pipeline (vista estilo n8n).

    Devuelve datos crudos y deja el semáforo al cliente: así los filtros (rango, solo
    errores, estado final) no obligan a reconstruir el JSON ni a volver a la base.

    ⚠ El nodo "plantilla enviada" se evalúa SIEMPRE desde send_log y NUNCA se deriva del
    `action` del webhook: las tandas de recuperación mandan por fuera del receptor, así que
    hay leads con envío real y sin fila SENT. Derivarlo los mostraría como no enviados.
    """
    sql = """
    WITH llegada AS (
      SELECT DISTINCT ON (phone) phone, received_at, nombre, nid, gestion, direccion, action
      FROM ventanas_hs_inbound
      WHERE action NOT LIKE 'DRY:%%' AND received_at > now() - make_interval(days => %s)
      ORDER BY phone, received_at DESC
    ),
    envio AS (
      SELECT DISTINCT ON (phone) phone, attempted_at, template, accepted
      FROM send_log WHERE template LIKE 'ventanas%%'
      ORDER BY phone, attempted_at DESC
    ),
    respuesta AS (
      SELECT phone, min(ts) AS primera_respuesta
      FROM agent_thread WHERE campaign='ventanas' AND role='user' GROUP BY phone
    ),
    cierre AS (
      SELECT DISTINCT ON (phone) phone, action_taken
      FROM agent_thread WHERE campaign='ventanas' AND role='assistant'
        AND action_taken IN ('BACKBONE','BACKBONE_FAILED','CLOSE_OPT_OUT',
                             'CLOSE_YA_CON_HABI','CLOSE_NO_CONSENT')
      ORDER BY phone, ts DESC
    )
    SELECT l.phone, to_char(l.received_at AT TIME ZONE 'America/Bogota','MM-DD HH24:MI') AS llegada,
           l.received_at, l.nombre, l.nid, l.gestion, l.direccion, l.action,
           e.template, e.accepted,
           to_char(e.attempted_at AT TIME ZONE 'America/Bogota','MM-DD HH24:MI') AS envio_hora,
           to_char(r.primera_respuesta AT TIME ZONE 'America/Bogota','MM-DD HH24:MI') AS respuesta_hora,
           i.consent, i.step, i.completed_at, i.lead_fired_at,
           c.action_taken AS cierre, rec.new_deal_id
    FROM llegada l
    LEFT JOIN envio e     ON e.phone = l.phone
    LEFT JOIN respuesta r ON r.phone = l.phone
    LEFT JOIN ventanas_intake i ON i.phone = l.phone AND i.country = 'CO'
    LEFT JOIN cierre c    ON c.phone = l.phone
    LEFT JOIN recreation rec ON rec.old_nid = l.nid
    ORDER BY l.received_at DESC
    """
    filas = N._rows(sql, (int(dias),))
    out = []
    for r in filas:
        out.append({
            "phone": r["phone"], "llegada": r["llegada"],
            "recibido": str(r["received_at"]),
            "nombre": r["nombre"], "nid": r["nid"], "gestion": r["gestion"],
            "direccion": bool(r["direccion"]), "action": r["action"],
            "template": r["template"], "accepted": r["accepted"], "envio_hora": r["envio_hora"],
            "respuesta_hora": r["respuesta_hora"],
            "consent": r["consent"], "step": r["step"],
            "completada": r["completed_at"] is not None,
            "lead_disparado": r["lead_fired_at"] is not None,
            "cierre": r["cierre"], "deal_id": r["new_deal_id"],
        })
    return out


def ventanas_serie(dias=14):
    """Llegadas, enviadas, respuestas y deals por día (calendario de Bogotá)."""
    TZ = "America/Bogota"
    def _serie(sql):
        return {r["d"]: int(r["n"]) for r in N._rows(sql, (int(dias),))}
    lleg = _serie(f"SELECT (received_at AT TIME ZONE '{TZ}')::date::text d, count(*) n "
                  "FROM ventanas_hs_inbound WHERE action NOT LIKE 'DRY:%%' "
                  "AND received_at > now() - make_interval(days => %s) GROUP BY 1")
    env = _serie(f"SELECT (attempted_at AT TIME ZONE '{TZ}')::date::text d, count(*) n "
                 "FROM send_log WHERE template LIKE 'ventanas%%' AND accepted "
                 "AND attempted_at > now() - make_interval(days => %s) GROUP BY 1")
    resp = _serie(f"SELECT (ts AT TIME ZONE '{TZ}')::date::text d, count(DISTINCT phone) n "
                  "FROM agent_thread WHERE campaign='ventanas' AND role='user' "
                  "AND ts > now() - make_interval(days => %s) GROUP BY 1")
    deal = _serie(f"SELECT (ts AT TIME ZONE '{TZ}')::date::text d, count(DISTINCT phone) n "
                  "FROM agent_thread WHERE campaign='ventanas' AND action_taken='BACKBONE' "
                  "AND ts > now() - make_interval(days => %s) GROUP BY 1")
    dias_set = sorted(set(lleg) | set(env) | set(resp) | set(deal))
    return [{"fecha": d, "llegadas": lleg.get(d, 0), "enviadas": env.get(d, 0),
             "respuestas": resp.get(d, 0), "deals": deal.get(d, 0)} for d in dias_set]


def ventanas_metricas():
    """Embudo del programa VENTANAS, según el spec de esa sesión (26-ago-2026).

    Ventanas es SOLO CO y no comparte semántica con el loop, así que no se puede medir con
    las mismas piezas:
      · La atribución de campaña es por PREFIJO DEL TEMPLATE ('ventanas%'), la misma regla que
        usa el agente para enrutar la respuesta. Si el tablero usara otra, mostraría una
        campaña mientras el agente contesta con otra.
      · `accepted` significa "Infobip aceptó", NO "llegó al teléfono": la entrega real vive en
        el mart de BigQuery. Por eso acá se rotula "enviadas" y nunca "entregadas".
      · "Respondieron" necesita UNIR contact_status (clicks de botón, que procesa el bot y
        nunca llegan a agent_thread) con agent_thread (texto libre, tiempo real). Medido con
        una sola fuente, el porcentaje anidado llegó a dar 733%.
      · `ventanas_hs_inbound.action LIKE 'DRY:%'` son pruebas en seco: se excluyen SIEMPRE.
      · El día es calendario de America/Bogota, no UTC.
    """
    TZ = "America/Bogota"
    ventanas_dias = {"hoy": 0, "7": 7, "30": 30}
    out = {"rangos": {}, "acciones": [], "intake": {}, "supresion": [], "pais": "CO"}

    def _desde(sql_col, dias):
        if dias == 0:
            return f"({sql_col} AT TIME ZONE '{TZ}')::date = (now() AT TIME ZONE '{TZ}')::date"
        return f"{sql_col} > now() - interval '{int(dias)} days'"

    with _SNC() as c:
        for k, d in ventanas_dias.items():
            recibidos = list(c.execute(
                "SELECT count(*) FROM ventanas_hs_inbound "
                "WHERE action NOT LIKE 'DRY:%%' AND " + _desde("received_at", d)))[0][0]
            enviadas = list(c.execute(
                "SELECT count(*) FROM send_log "
                "WHERE template LIKE 'ventanas%%' AND accepted AND " + _desde("attempted_at", d)))[0][0]
            # Respondieron = clicks de botón (contact_status) UNIDO a texto libre (agent_thread).
            respondieron = list(c.execute(
                "WITH ultimo_envio AS ("
                "  SELECT DISTINCT ON (phone) phone,"
                "         CASE WHEN template LIKE 'ventanas%%' THEN 'ventanas' ELSE 'otra' END AS campania"
                "  FROM send_log WHERE accepted ORDER BY phone, attempted_at DESC),"
                "por_boton AS ("
                "  SELECT cs.phone, u.campania, cs.responded_at AS cuando"
                "  FROM contact_status cs JOIN ultimo_envio u ON u.phone = cs.phone"
                "  WHERE cs.responded_at IS NOT NULL),"
                "por_texto AS ("
                "  SELECT phone, 'ventanas' AS campania, ts AS cuando"
                "  FROM agent_thread WHERE campaign = 'ventanas' AND role = 'user')"
                "SELECT count(DISTINCT phone) FROM ("
                "  SELECT * FROM por_boton UNION SELECT * FROM por_texto) t "
                "WHERE campania = 'ventanas' AND " + _desde("cuando", d)))[0][0]
            atendidos = list(c.execute(
                "SELECT count(DISTINCT phone) FROM agent_thread "
                "WHERE campaign='ventanas' AND role='user' AND " + _desde("ts", d)))[0][0]
            deal_ok = list(c.execute(
                "SELECT count(DISTINCT phone) FROM agent_thread "
                "WHERE campaign='ventanas' AND action_taken IN ('BACKBONE','BACKBONE_SANITIZED') "
                "AND " + _desde("ts", d)))[0][0]
            deal_no = list(c.execute(
                "SELECT count(DISTINCT phone) FROM agent_thread "
                "WHERE campaign='ventanas' AND action_taken='BACKBONE_FAILED' "
                "AND " + _desde("ts", d)))[0][0]
            out["rangos"][k] = {"recibidos": recibidos, "enviadas": enviadas,
                                "respondieron": respondieron, "atendidos": atendidos,
                                "deal_creado": deal_ok, "deal_fallo": deal_no}

        # Desenlace de cada POST del webhook. TERMINAL y DEDUP son GUARDAS funcionando, no
        # fallas: van glosadas, no en rojo. Rojo solo lo que es config rota o rechazo real.
        PROBLEMA = {"SEND_FAIL", "NO_TEMPLATE", "TEMPLATE_NO_VENTANAS", "SIN_DIRECCION", "BAD_PHONE"}
        GUARDA = {"DEDUP", "TERMINAL", "PROGRAMA_AJENO"}
        for r in c.execute(
                "SELECT action, count(*) FROM ventanas_hs_inbound "
                "WHERE action NOT LIKE 'DRY:%%' GROUP BY 1 ORDER BY 2 DESC"):
            a = r[0] or "(sin action)"
            out["acciones"].append({"action": a, "n": r[1],
                                    "tipo": "ok" if a == "SENT" else
                                            ("problema" if a in PROBLEMA else
                                             ("guarda" if a in GUARDA else "otro"))})

        fila = list(c.execute(
            "SELECT count(*) FILTER (WHERE step='consent') AS esperando_consent,"
            "       count(*) FILTER (WHERE consent AND step IS NOT NULL AND completed_at IS NULL) AS en_entrevista,"
            "       count(*) FILTER (WHERE completed_at IS NOT NULL) AS completadas,"
            "       count(*) FILTER (WHERE lead_fired_at IS NOT NULL) AS con_deal,"
            "       count(*) FILTER (WHERE completed_at IS NOT NULL AND lead_fired_at IS NULL) AS cerradas_sin_deal,"
            "       count(*) FILTER (WHERE reengage_count > 0) AS reenganchadas "
            "FROM ventanas_intake WHERE country='CO'"))[0]
        out["intake"] = dict(zip(("esperando_consent", "en_entrevista", "completadas",
                                  "con_deal", "cerradas_sin_deal", "reenganchadas"), map(int, fila)))

        for r in c.execute("SELECT motivo, count(*) FROM ventanas_supresion "
                           "WHERE country='CO' GROUP BY 1 ORDER BY 2 DESC LIMIT 10"):
            out["supresion"].append({"motivo": r[0] or "(sin motivo)", "n": r[1]})
    return out


def agente_acciones(pais, dias=30):
    """Desenlace de los turnos del agente (últimos `dias`): qué hizo con cada conversación.
    Alimenta la pantalla Agente IA del panel. SHADOW y NOT_IN_SAMPLE se muestran aparte
    porque ahí el agente propone pero NO manda: no son desenlaces suyos."""
    rows = N._rows(
        "SELECT coalesce(action_taken,'(sin accion)') AS accion, count(*) AS n, "
        "       count(DISTINCT phone) AS telefonos "
        "FROM agent_thread WHERE country=%s AND role='assistant' "
        "  AND ts > now() - make_interval(days => %s) GROUP BY 1 ORDER BY 2 DESC",
        (pais, int(dias)))
    return [{"accion": r["accion"], "n": int(r["n"]), "telefonos": int(r["telefonos"])} for r in rows]


def agente_ia(pais):
    """Usuarios reasignados por el agente SDR de IA (conversacional, texto libre): sellers cuyo
    hilo con el agente terminó en BACKBONE — respuesta positiva directa o movido a interesado
    durante la conversación — y el lead se recreó en el backbone. Por día local del país.
    Fuente: Neon agent_thread (turnos del agente EN VIVO; los SHADOW no cuentan)."""
    rows = N._rows("""
        SELECT (ts AT TIME ZONE %s)::date::text AS fecha,
               count(DISTINCT phone) FILTER (WHERE action_taken IN ('BACKBONE','BACKBONE_SANITIZED')) AS reasignados,
               count(DISTINCT phone) FILTER (WHERE intent='INTERESTED') AS interesados,
               count(DISTINCT phone) AS conversaciones
        FROM agent_thread
        WHERE country=%s AND role='assistant'
        GROUP BY 1 ORDER BY 1""", (N.TZ[pais], pais))
    return [{"fecha": r["fecha"], "reasignados": int(r["reasignados"] or 0),
             "interesados": int(r["interesados"] or 0),
             "conversaciones": int(r["conversaciones"] or 0)} for r in rows]

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
  "pool_ab": {"MX": _pool_ab("MX"), "CO": _pool_ab("CO")},
  "inventario": {"MX": _inventario("MX"), "CO": _inventario("CO")},
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
  # KPIs de cabecera: contactados sale de Neon (entrega real) y el resto de BQ, cada
  # métrica por su propia fecha (creado / cita / cierre). Ver query_kpis.sql.
  "contactados": {"MX": mx["contactados"], "CO": co["contactados"]},
  "panel": {"MX": mx["panel"], "CO": co["panel"]},
  # OJO: acá NO va `ejecuciones` (nombre, nid, teléfono). data.json es público y se
  # descarga sin auth; esos datos los sirve /api/ventanas/ejecuciones detrás del token.
  "ventanas": {**ventanas_metricas(), "serie": ventanas_serie()},
  "plantillas": {"MX": mx["plantillas"], "CO": co["plantillas"]},
  "reasignados_dia": {"MX": mx["reasignados_dia"], "CO": co["reasignados_dia"]},
  # citas y cierres por rango, indexados pais -> rango
  "panel_bq": (lambda rows: {p: {str(r["dias"]): {k: int(r[k] or 0) for k in ("citas","cierres_mm","cierres_inmo")}
                                 for r in rows if r["pais"] == p}
                             for p in ("MX","CO")})(q("query_panel.sql")),
  "kpis": {r["pais"]: r for r in q("query_kpis.sql")},
  "cosecha_agente": {"MX": mx["cosecha_agente"], "CO": co["cosecha_agente"]},
  "agente_conversaciones": {"MX": mx["agente_conversaciones"], "CO": co["agente_conversaciones"]},
  "agente_ia": {"MX": agente_ia("MX"), "CO": agente_ia("CO")},
  "agente_acciones": {"MX": agente_acciones("MX"), "CO": agente_acciones("CO")},
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
