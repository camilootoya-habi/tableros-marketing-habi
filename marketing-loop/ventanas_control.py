"""Ventanas · tabla de control (spec docs/superpowers/specs/2026-09-07-ventanas-tabla-control-design.md).

Dos capas a propósito:
  · PURA  — ruta(), es_habil(), madura(), mediana(), construir(raw, hoy, ahora): listas de dicts
            → JSON de `ventanas.control`. Sin base. Es lo que se prueba.
  · SQL   — extraer(), bloque4(): consultas a Neon que devuelven filas planas con la fecha ya en
            calendario de Bogotá. control() orquesta y nunca propaga: si Neon falla, devuelve
            {"error": ...} y el resto del data.json sale igual.
"""
import datetime
import statistics
from collections import Counter, defaultdict

TZ = "America/Bogota"
RUTAS = ("compra_directa", "tibio", "nocontesta")
PRIMER_ENVIO = {"ventanas_nocontesta_co_v1", "ventanas_compra_co_v1", "ventanas_tibio_co_v1"}
SEGUIMIENTO = {"ventanas_reenganche_co_v1"}
# Acciones del webhook que NO son SENT ni DEDUP: fallas (rojo) y guardas (gris). El front colorea.
FALLA = {"SIN_DIRECCION", "NO_TEMPLATE", "SEND_FAIL", "BAD_PHONE", "TEMPLATE_NO_VENTANAS"}
GUARDA = {"TERMINAL", "CAP_DIARIO", "FUERA_HORARIO", "DEDUP", "PROGRAMA_AJENO"}
DIAS_MADUREZ = 4          # cubre el reloj de 72 h
REF_DIAS = 7              # últimos N días hábiles maduros para la referencia
REF_MIN_COHORTE = 5       # cohortes más chicas no entran a la referencia de %
COLS_REF_B1 = ("posts", "personas", "nuevas")
COLS_REF_B3 = ("cohorte", "respondieron", "consintieron", "entrevista_completa", "deal_completo")


# ----------------------------------------------------------------------------- PURA
def ruta(flujo, kind, gestion):
    """Ruta por teléfono: flujo primero, kind después (regla de la sesión VENTANAS, 7-sep).
    El ILIKE sobre la gestión cubre las filas de recuperación que llegan con kind vacío."""
    if (flujo or "") == "compra_wa":
        return "compra_directa"
    if (kind or "") == "whatsapp" or "whatsapp" in (gestion or "").lower():
        return "tibio"
    return "nocontesta"


def _ruta_por_template(t):
    t = t or ""
    return "compra_directa" if "compra" in t else ("tibio" if "tibio" in t else "nocontesta")


def es_habil(fecha_iso):
    return datetime.date.fromisoformat(fecha_iso).weekday() < 5


def madura(fecha_iso, hoy_iso):
    return (datetime.date.fromisoformat(hoy_iso) - datetime.date.fromisoformat(fecha_iso)).days >= DIAS_MADUREZ


def mediana(valores):
    v = [x for x in valores if x is not None]
    return statistics.median(v) if v else None


def _semana_iso(fecha_iso):
    y, w, _ = datetime.date.fromisoformat(fecha_iso).isocalendar()
    return f"{y}-W{w:02d}"


def _pct(n, d):
    return round(n / d * 100, 1) if d else None


def construir(raw, hoy_iso, ahora_hhmm):
    """raw → ventanas.control (sin `agente`, que sale de SQL directo). Ver docstring del módulo
    y el plan para el shape exacto de `raw`."""
    hs = sorted(raw.get("hs", []), key=lambda r: r["ts"])
    env = raw.get("env", [])
    resp, consent, completa = raw.get("resp", set()), raw.get("consent", set()), raw.get("completa", set())
    deal_ok, deal_fallo = raw.get("deal_ok", {}), raw.get("deal_fallo", {})
    handoff, optout, lead_fired = raw.get("handoff", {}), raw.get("optout", set()), raw.get("lead_fired", {})
    delivered = raw.get("delivered", set())

    # Primer POST por teléfono (incluye RECUPERADO): define cohorte y ruta.
    primero = {}
    primero_hs = {}          # primer POST del WORKFLOW (sin RECUPERADO): define "personas nuevas"
    for r in hs:
        primero.setdefault(r["phone"], r)
        if not (r["action"] or "").startswith("RECUPERADO"):
            primero_hs.setdefault(r["phone"], r)
    ruta_de = {p: ruta(r["flujo"], r["kind"], r["gestion"]) for p, r in primero.items()}
    def ruta_env(r):
        return ruta_de.get(r["phone"]) or _ruta_por_template(r["template"])

    fechas = [r["fecha"] for r in hs] + [r["fecha"] for r in env]
    ini = datetime.date.fromisoformat(min(fechas)) if fechas else datetime.date.fromisoformat(hoy_iso)
    fin = datetime.date.fromisoformat(hoy_iso)
    dias_iso = [(ini + datetime.timedelta(days=i)).isoformat() for i in range((fin - ini).days + 1)]

    # Índices por día
    hs_dia = defaultdict(list)
    for r in hs:
        if not (r["action"] or "").startswith("RECUPERADO"):
            hs_dia[r["fecha"]].append(r)
    env_dia = defaultdict(list)
    for r in env:
        env_dia[r["fecha"]].append(r)
    coh_dia = defaultdict(list)
    for p, r in primero.items():
        coh_dia[r["fecha"]].append(p)

    def en_ruta(p_or_r, rt, es_env=False):
        if rt == "todas":
            return True
        return (ruta_env(p_or_r) if es_env else ruta_de.get(p_or_r)) == rt

    def b1(fecha, rt):
        rows = [r for r in hs_dia[fecha] if en_ruta(r["phone"], rt)]
        posts = len(rows)
        dedup = sum(1 for r in rows if r["action"] == "DEDUP")
        nuevas = sum(1 for p, r in primero_hs.items() if r["fecha"] == fecha and en_ruta(p, rt))
        bloq = Counter(r["action"] for r in rows if r["action"] not in ("SENT", "DEDUP"))
        return {"posts": posts, "personas": len({r["phone"] for r in rows}), "nuevas": nuevas,
                "dedup_pct": _pct(dedup, posts), "bloqueos": dict(bloq),
                "ultimo_post": max((r["hora"] for r in rows), default=None)}

    def b2(fecha, rt):
        rows = [r for r in env_dia[fecha] if en_ruta(r, rt, es_env=True)]
        return {"primer_envio": sum(1 for r in rows if r["accepted"] and r["template"] in PRIMER_ENVIO),
                "seguimientos": sum(1 for r in rows if r["accepted"] and r["template"] in SEGUIMIENTO),
                "rechazos": sum(1 for r in rows if not r["accepted"])}

    def b3(fecha, rt, es_madura):
        ph = [p for p in coh_dia[fecha] if en_ruta(p, rt)]
        completo = sum(1 for p in ph if deal_ok.get(p) is True)
        codes = sorted(c for p in ph for c in deal_fallo.get(p, []))
        horas = []
        for p in ph:
            if p in lead_fired:
                t0 = datetime.datetime.fromisoformat(primero[p]["ts"])
                t1 = datetime.datetime.fromisoformat(lead_fired[p])
                horas.append((t1 - t0).total_seconds() / 3600)
        n = len(ph)
        return {"cohorte": n,
                "recuperados": sum(1 for p in ph if (primero[p]["action"] or "").startswith("RECUPERADO")),
                "respondieron": sum(1 for p in ph if p in resp),
                "consintieron": sum(1 for p in ph if p in consent),
                "entrevista_completa": sum(1 for p in ph if p in completa),
                "deal_completo": completo,
                "deal_parcial": sum(1 for p in ph if deal_ok.get(p) is False),
                "deal_fallo": sum(1 for p in ph if p in deal_fallo), "deal_fallo_codes": codes,
                "handoff_sin_respuesta": sum(1 for p in ph if handoff.get(p) == "SIN_RESPUESTA_24H"),
                "handoff_pide_llamada": sum(1 for p in ph if handoff.get(p) == "PIDE_LLAMADA"),
                "optout": sum(1 for p in ph if p in optout),
                "conversion_total": _pct(completo, n) if (es_madura and n) else None,
                "horas_a_deal": round(mediana(horas), 1) if horas else None}

    dias = []
    for f in dias_iso:
        m = madura(f, hoy_iso)
        d = {"fecha": f, "habil": es_habil(f), "madura": m, "hoy": f == hoy_iso}
        for rt in ("todas",) + RUTAS:
            d[rt] = {"b1": b1(f, rt), "b2": b2(f, rt), "b3": b3(f, rt, m)}
        dias.append(d)

    # Semanal: primer envío y entregados (message_id en el mart) por semana ISO y ruta
    sem = defaultdict(lambda: {rt: {"primer_envio": 0, "entregados": 0} for rt in ("todas",) + RUTAS})
    for r in env:
        if not (r["accepted"] and r["template"] in PRIMER_ENVIO):
            continue
        for rt in ("todas", ruta_env(r)):
            sem[_semana_iso(r["fecha"])][rt]["primer_envio"] += 1
            if r["message_id"] in delivered:
                sem[_semana_iso(r["fecha"])][rt]["entregados"] += 1
    semanas = [{"semana": k, **v} for k, v in sorted(sem.items())]

    plantillas = [{"nombre": p["nombre"], "estado": p.get("estado"),
                   "aprobada": p.get("estado") == "APPROVED"} for p in raw.get("plantillas", [])]

    # Referencia: mediana de los últimos REF_DIAS días hábiles maduros, por ruta y columna
    ref_dias = [d for d in reversed(dias) if d["habil"] and d["madura"]][:REF_DIAS]
    referencia = {}
    for rt in ("todas",) + RUTAS:
        col = {}
        for c in COLS_REF_B1:
            col[c] = mediana([d[rt]["b1"][c] for d in ref_dias])
        col["primer_envio"] = mediana([d[rt]["b2"]["primer_envio"] for d in ref_dias])
        for c in COLS_REF_B3:
            col[c] = mediana([d[rt]["b3"][c] for d in ref_dias])
        col["conversion_total"] = mediana([d[rt]["b3"]["conversion_total"] for d in ref_dias
                                           if d[rt]["b3"]["cohorte"] >= REF_MIN_COHORTE])
        referencia[rt] = col

    return {"generado": f"{hoy_iso}T{ahora_hhmm}", "rutas": list(RUTAS), "dias": dias,
            "semanas": semanas, "plantillas": plantillas, "referencia": referencia}


# ----------------------------------------------------------------------------- SQL
def extraer(N, M):
    """Filas planas de Neon (+ entregados del mart de BigQuery) con fechas en Bogotá."""
    loc = lambda col: f"({col} AT TIME ZONE '{TZ}')"
    hs = N._rows(f"""
        SELECT phone, to_char({loc('received_at')},'YYYY-MM-DD') AS fecha,
               to_char({loc('received_at')},'HH24:MI') AS hora,
               to_char({loc('received_at')},'YYYY-MM-DD"T"HH24:MI:SS') AS ts,
               action, flujo, kind, gestion, template
        FROM ventanas_hs_inbound
        WHERE action NOT LIKE 'DRY:%%' AND phone IS NOT NULL ORDER BY received_at""")
    env = N._rows(f"""
        SELECT phone, to_char({loc('attempted_at')},'YYYY-MM-DD') AS fecha, template,
               coalesce(accepted,false) AS accepted, message_id
        FROM send_log WHERE template LIKE 'ventanas%%'""")
    # Respondieron = texto libre al agente ∪ clics de botón (contact_status), estos últimos solo
    # si el último envío aceptado del teléfono fue de ventanas (misma regla que ventanas_metricas).
    resp = {r["phone"] for r in N._rows("""
        SELECT DISTINCT phone FROM agent_thread WHERE campaign='ventanas' AND role='user'
        UNION
        SELECT cs.phone FROM contact_status cs
        JOIN (SELECT DISTINCT ON (phone) phone, template FROM send_log WHERE accepted
              ORDER BY phone, attempted_at DESC) u ON u.phone = cs.phone
        WHERE cs.responded_at IS NOT NULL AND u.template LIKE 'ventanas%%'""")}
    intake = N._rows(f"""
        SELECT phone, consent, step, completed_at,
               to_char({loc('lead_fired_at')},'YYYY-MM-DD"T"HH24:MI:SS') AS lead_fired
        FROM ventanas_intake WHERE country='CO'""")
    step_nulo = {r["phone"]: r["step"] is None for r in intake}
    bb = N._rows("SELECT phone, resultado, http_code FROM ventanas_backbone_intento WHERE country='CO' ORDER BY created_at")
    deal_ok, deal_fallo = {}, defaultdict(list)
    for r in bb:
        if r["resultado"] == "BACKBONE":
            # completo si el intake quedó sin slot pendiente (sin fila de intake = completo)
            deal_ok[r["phone"]] = deal_ok.get(r["phone"]) or step_nulo.get(r["phone"], True)
        elif r["resultado"] == "BACKBONE_FAILED":
            deal_fallo[r["phone"]].append(str(r["http_code"] or "?"))
    for p in deal_ok:               # si al final quedó creado, no se cuenta como fallo
        deal_fallo.pop(p, None)
    return {
        "hs": hs, "env": env, "resp": resp,
        "consent": {r["phone"] for r in intake if r["consent"]},
        "completa": {r["phone"] for r in intake if r["completed_at"] is not None and r["step"] is None},
        "lead_fired": {r["phone"]: r["lead_fired"] for r in intake if r["lead_fired"]},
        "deal_ok": deal_ok, "deal_fallo": dict(deal_fallo),
        "handoff": {r["phone"]: r["motivo"] for r in N._rows(
            "SELECT phone, motivo FROM ventanas_dapta_handoff WHERE country='CO'")},
        "optout": {r["phone"] for r in N._rows(
            "SELECT DISTINCT phone FROM agent_thread WHERE campaign='ventanas' AND action_taken='CLOSE_OPT_OUT'")},
        "delivered": {mid for mid, v in M.mart_by_msgid(90, country="CO").items()
                      if (v or {}).get("status") == "delivered"},
    }


def bloque4(N):
    """Salud del agente por día (Bogotá) + cola de entrevistas abiertas (foto de ahora).
    Los turnos SHADOW no cuentan: ahí el agente propone pero no manda."""
    loc = f"(ts AT TIME ZONE '{TZ}')::date::text"
    atasc = {r["fecha"]: int(r["n"]) for r in N._rows(f"""
        WITH t AS (SELECT phone, {loc} AS fecha, content,
                          lag(content)   OVER (PARTITION BY phone ORDER BY ts, turn_idx) AS p1,
                          lag(content,2) OVER (PARTITION BY phone ORDER BY ts, turn_idx) AS p2
                   FROM agent_thread WHERE campaign='ventanas' AND role='assistant'
                     AND coalesce(action_taken,'') NOT LIKE 'SHADOW%%')
        SELECT fecha, count(DISTINCT phone) AS n FROM t WHERE content=p1 AND content=p2 GROUP BY 1""")}
    lat = {r["fecha"]: round(float(r["lat"]), 1) for r in N._rows(f"""
        WITH t AS (SELECT phone, role, ts,
                          lag(role) OVER (PARTITION BY phone ORDER BY ts, turn_idx) AS prole,
                          lag(ts)   OVER (PARTITION BY phone ORDER BY ts, turn_idx) AS pts
                   FROM agent_thread WHERE campaign='ventanas'
                     AND coalesce(action_taken,'') NOT LIKE 'SHADOW%%')
        SELECT {loc} AS fecha,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM ts - pts)) AS lat
        FROM t WHERE role='assistant' AND prole='user' GROUP BY 1""") if r["lat"] is not None}
    err = {r["fecha"]: int(r["n"]) for r in N._rows(f"""
        SELECT {loc} AS fecha, count(*) AS n FROM agent_thread
        WHERE campaign='ventanas' AND action_taken IN ('TURN_ERROR','LLM_ERROR') GROUP BY 1""")}
    abiertas = N._rows("""
        SELECT count(*) AS n FROM ventanas_intake
        WHERE country='CO' AND consent AND step IS NOT NULL
          AND last_inbound_at > now() - interval '72 hours' AND lead_fired_at IS NULL""")[0]["n"]
    fechas = sorted(set(atasc) | set(lat) | set(err))
    return {"agente": [{"fecha": f, "atascadas": atasc.get(f, 0), "latencia_s": lat.get(f),
                        "errores": err.get(f, 0)} for f in fechas],
            "abiertas": int(abiertas)}


def control(plantillas, M):
    """Orquesta todo. Nunca propaga: con Neon caído devuelve {"error"} y el build sigue."""
    from zoneinfo import ZoneInfo
    import sources_neon as N
    ahora = datetime.datetime.now(ZoneInfo(TZ))
    hoy, hhmm = ahora.date().isoformat(), ahora.strftime("%H:%M")
    try:
        raw = extraer(N, M)
        raw["plantillas"] = [p for p in (plantillas or []) if (p.get("nombre") or "").startswith("ventanas")]
        out = construir(raw, hoy, hhmm)
        out.update(bloque4(N))
        return out
    except Exception as e:  # noqa: BLE001 — el resto del data.json no depende de esto
        print(f"WARN ventanas_control: {e}")
        return {"error": str(e), "generado": f"{hoy}T{hhmm}"}
