#!/usr/bin/env python3
"""Build tablero-marketing/web_data.json (hoja "Funnel WEB") desde 3 salidas de BQ.

Migrado desde funnel-web-mx/build_data.py (2026-09-02), extendido a CO+MX y a las
6 granularidades del tablero. Know-how: docs/marketing/puentes-datos-web.md

Cada granularidad viene YA agregada de BigQuery: las métricas son COUNT(DISTINCT)
de visitantes y de nids, que NO se pueden sumar entre períodos.

Usage:
  python3 build_web_data.py clicks.json sessions.json leads.json rutas.json referrers.json otp_salud.json otp_ab.json web_data.json
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

PAISES = ["CO", "MX"]
GRANS = ["D", "W", "C", "M", "Q", "Y"]

# Estructura REAL del formulario, medida sobre recorridos de agosto 2026 (excluyendo
# la entrada anómala por Google, ver abajo). Dos bloques:
#
#   TRONCO  — pasos por los que pasa >=85% de quien completa el registro.
#             Mismo conjunto en los dos países; el orden dentro sí es idéntico.
#   RAMAS   — pasos opcionales. % de los que completan que pasa por ahí:
#             CO: datos 73,8% · confirmar_ubicacion 30,4% · sugerencias 21,6%
#             MX: confirmar_ubicacion 79,4% · datos 78,4% · sugerencias 75,7%
#             Se separan porque su "caída" no es abandono: es gente que no los necesita.
#
# ⚠️ Anomalía SEO (CO, confirmada 2026-09-02): `/formulario-inmueble/caracteristicas`
#    está INDEXADA en Google y recibe tráfico orgánico directo — ~714 personas/mes entran
#    en frío a mitad del formulario y se registran sin pasar por el primer paso (0,3% tiene
#    `funnel_entry_next`, contra 100% de quien entra bien: no es hueco de tracking).
#    Por eso `form_top` NO cubre al 100% de los registros en CO (89,5%). El orden de la
#    tabla se derivó EXCLUYENDO esos casos. Las URLs interiores deberían llevar `noindex`.
# Path real de cada etapa por país (verificado a mano 2026-09-02: desde el home,
# CO abre el formulario en /direccion y MX en /inicio). Se muestra bajo la etiqueta
# para que la tabla sea auto-explicativa sin abrir el modal.
PATHS = {
    "CO": {"form_top": "/direccion", "zona": "/inmuebles-zona", "contacto": "/contacto",
           "caracteristicas": "/caracteristicas", "ultimos_detalles": "/ultimos-detalles",
           "felicitaciones": "/felicitaciones", "sugerencias": "/sugerencias",
           "datos_inmueble": "/datos-inmueble", "confirmar_ubicacion": "/confirmar-ubicacion"},
    "MX": {"form_top": "/inicio", "zona": "/inmuebles-zona", "contacto": "/contacto",
           "caracteristicas": "/caracteristicas", "ultimos_detalles": "/ultimos-detalles",
           "felicitaciones": "/felicitaciones", "sugerencias": "/sugerencias-de-propiedades +/editar",
           "datos_inmueble": "/datos-inmueble", "confirmar_ubicacion": "/confirmar-ubicacion-mx"},
}

TRONCO = ["session", "form_top", "zona", "contacto", "caracteristicas",
          "ultimos_detalles", "felicitaciones"]
RAMAS = {
    "CO": ["sugerencias", "datos_inmueble", "confirmar_ubicacion"],
    "MX": ["confirmar_ubicacion", "datos_inmueble", "sugerencias"],
}
ORDER = {p: TRONCO + RAMAS[p] for p in ("CO", "MX")}

STAGES = [
    {"id": "click",               "label": "Click reportado",       "supports": ["canal_plat"]},
    {"id": "session",             "label": "Sesión Segment",        "supports": ["canal_plat", "device"]},
    {"id": "form_top",            "label": "Inicio del formulario", "supports": ["canal_plat", "device"]},
    {"id": "zona",                "label": "Inmuebles / zona",      "supports": ["canal_plat", "device"]},
    {"id": "confirmar_ubicacion", "label": "Confirmar ubicación",   "supports": ["canal_plat", "device"]},
    {"id": "datos_inmueble",      "label": "Datos del inmueble",    "supports": ["canal_plat", "device"]},
    {"id": "caracteristicas",     "label": "Características",       "supports": ["canal_plat", "device"]},
    {"id": "ultimos_detalles",    "label": "Últimos detalles",      "supports": ["canal_plat", "device"]},
    {"id": "sugerencias",         "label": "Sugerencias",           "supports": ["canal_plat", "device"]},
    {"id": "contacto",            "label": "Contacto",              "supports": ["canal_plat", "device"]},
    {"id": "felicitaciones",      "label": "Form completado",       "supports": ["canal_plat", "device"]},
    {"id": "lead",                "label": "Lead registrado",       "supports": ["canal_plat", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "calificado",          "label": "Calificado",            "supports": ["canal_plat", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "asignado",            "label": "Asignado",              "supports": ["canal_plat", "ciudad", "zona_grande", "zona_mediana"]},
]
STAGE_IDS = [s["id"] for s in STAGES]
DIMS = ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]

# Los cortes geográficos solo se guardan para la granularidad por defecto: guardarlos
# para las 6 multiplicaría el JSON por ~6 sin que nadie mire ciudad en vista anual.
GEO_DIMS = {"ciudad", "zona_grande", "zona_mediana"}
GEO_GRAN = "W"


def zeros():
    return {sid: 0 for sid in STAGE_IDS}


def main(clicks_path, sessions_path, leads_path, rutas_path, referrers_path,
         otp_salud_path, otp_ab_path, out_path):
    clicks = json.load(open(clicks_path))
    sessions = json.load(open(sessions_path))
    leads = json.load(open(leads_path))
    rutas = json.load(open(rutas_path))
    referrers = json.load(open(referrers_path))
    otp_salud = json.load(open(otp_salud_path))
    otp_ab = json.load(open(otp_ab_path))

    # store[pais][gran][periodo] -> {"totals": {...}, "by_<dim>": {val: {...}}}
    store = {p: {g: defaultdict(lambda: {"totals": zeros(),
                                         **{"by_" + d: defaultdict(zeros) for d in DIMS}})
                 for g in GRANS} for p in PAISES}

    def add(pais, gran, periodo, stage, n, dims):
        if pais not in store or gran not in GRANS or not n:
            return
        cell = store[pais][gran][periodo]
        cell["totals"][stage] += n
        for dim, val in dims.items():
            if val is None:
                continue
            if dim in GEO_DIMS and gran != GEO_GRAN:
                continue
            cell["by_" + dim][val][stage] += n

    for r in clicks:
        plat = r["plataforma"]
        cp = f"{plat}/Paid" if plat != "Otro" else "Otro/Otro"
        add(r["pais"], r["gran"], r["periodo"], "click", int(r["clicks"]), {"canal_plat": cp})

    for r in sessions:
        if r["stage"] not in STAGE_IDS:
            continue
        add(r["pais"], r["gran"], r["periodo"], r["stage"], int(r["n"]),
            {"canal_plat": r["canal_plat"], "device": r["device"]})

    for r in leads:
        dims = {"canal_plat": r["canal_plat"], "ciudad": r["ciudad"],
                "zona_grande": r["zona_grande"], "zona_mediana": r["zona_mediana"]}
        for stage, key in (("lead", "n_leads"), ("calificado", "n_calificados"), ("asignado", "n_asignados")):
            add(r["pais"], r["gran"], r["periodo"], stage, int(r.get(key) or 0), dims)

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stages": STAGES,
        "paises": PAISES,
        "grans": GRANS,
        "order": ORDER,
        "paths": PATHS,
        "tronco": TRONCO,
        "ramas": RAMAS,
        # rutas[pais][gran] = {periodo, total, filas:[{ruta, pasos, n, fin}]}
        "rutas": {},
        "geo_gran": GEO_GRAN,
        "by_country": {},
    }
    for p in PAISES:
        out["by_country"][p] = {"by_gran": {}}
        for g in GRANS:
            periods = sorted(store[p][g].keys())
            out["by_country"][p]["by_gran"][g] = {
                "periods": periods,
                "by_period": {
                    per: {"totals": store[p][g][per]["totals"],
                          **{"by_" + d: {k: v for k, v in store[p][g][per]["by_" + d].items()}
                             for d in DIMS}}
                    for per in periods
                },
            }

    # --- TRÁFICO: sesiones por referrer y canal (no cosechas: incluye recurrentes) ---
    # rf[pais][gran] = {periods, hosts:[{host,tipo,total,vals,nuevas,porCanal}], canales:{...}}
    rf = {p: {} for p in PAISES}
    for r in referrers:
        pais, gran = r["pais"], r["gran"]
        if pais not in rf:
            continue
        b = rf[pais].setdefault(gran, {"periods": set(), "hosts": {}, "canales": {}})
        per, ses, nue, canal = r["periodo"], int(r["sesiones"]), int(r["sesiones_nuevas"]), r["canal"]
        b["periods"].add(per)
        h = b["hosts"].setdefault(r["host"], {"host": r["host"], "tipo": r["tipo"], "total": 0,
                                              "vals": {}, "nuevas": {}, "porCanal": {}})
        h["vals"][per] = h["vals"].get(per, 0) + ses
        h["nuevas"][per] = h["nuevas"].get(per, 0) + nue
        h["total"] += ses
        h["porCanal"].setdefault(canal, {})
        h["porCanal"][canal][per] = h["porCanal"][canal].get(per, 0) + ses
        b["canales"].setdefault(canal, {})
        b["canales"][canal][per] = b["canales"][canal].get(per, 0) + ses
    for pais in rf:
        for gran, b in rf[pais].items():
            b["periods"] = sorted(b["periods"])
            b["hosts"] = sorted(b["hosts"].values(), key=lambda x: -x["total"])
    out["referrers"] = rf

    # --- recorridos reales dentro del formulario (último período cerrado) ---
    rt = {p: {} for p in PAISES}
    for r in rutas:
        pais, gran = r["pais"], r["gran"]
        if pais not in rt:
            continue
        b = rt[pais].setdefault(gran, {"periodo": r["periodo"], "filas": []})
        b["filas"].append({"ruta": r["ruta"], "pasos": int(r["pasos_n"]),
                           "n": int(r["visitantes"]),
                           "lead": int(r["con_lead"]),
                           "fin": r["termina_en_registro"] in (True, "true")})
    for pais in rt:
        for gran, b in rt[pais].items():
            b["filas"].sort(key=lambda x: -x["n"])
            b["total"] = sum(x["n"] for x in b["filas"])
            b["total_lead"] = sum(x["lead"] for x in b["filas"])
            b["total_fin"] = sum(x["n"] for x in b["filas"] if x["fin"])
    out["rutas"] = rt

    # ── OTP ───────────────────────────────────────────────────────────────────
    # Salud diaria: el embudo del propio OTP y por qué se cae la gente.
    salud = {p: [] for p in PAISES}
    for r in otp_salud:
        if r["pais"] not in salud:
            continue
        salud[r["pais"]].append({
            "dia": r["dia"], "regimen": r["regimen"],
            "req": int(r["requests"]), "ok": int(r["validan"]),
            "abandona": int(r["abandona_sin_intentar"]), "falla": int(r["intenta_y_falla"]),
            "agotado": int(r["intentos_agotados"]), "reenvio": int(r["pide_reenvio"]),
            "tope": int(r["tope_reenvios"]), "envio_fallido": int(r["envio_fallido"]),
        })
    for p in salud:
        salud[p].sort(key=lambda x: x["dia"])

    # Comparación por régimen. ⚠️ NO es un A/B válido: `con_otp` se deriva de
    # `otp_request_sent`, que se dispara AL ENVIAR el formulario — así que el brazo
    # tratado son "los que enviaron" y el control son "todos los que pisaron /contacto",
    # incluyendo a quien nunca envió. Los denominadores no son comparables y por eso el
    # resultado sale invertido (con OTP parece convertir el doble). Se guarda para
    # mostrarlo COMO ADVERTENCIA en el tablero, no como resultado.
    ab = {p: {} for p in PAISES}
    for r in otp_ab:
        pais = r["pais"]
        if pais not in ab:
            continue
        b = ab[pais].setdefault(r["regimen"], {})
        k = "con" if r["con_otp"] in (1, "1", True, "true") else "sin"
        c = b.setdefault(k, {"contacto": 0, "valida": 0, "caract": 0, "felic": 0, "lead": 0, "calif": 0})
        c["contacto"] += int(r["n_contacto"]); c["valida"] += int(r["valida_otp"])
        c["caract"] += int(r["n_caracteristicas"]); c["felic"] += int(r["n_felicitaciones"])
        c["lead"] += int(r["n_lead"]); c["calif"] += int(r["n_calificado"])

    out["otp"] = {"salud": salud, "ab": ab}

    with open(out_path, "w") as f:
        json.dump(out, f, separators=(",", ":"))

    for p in PAISES:
        w = out["by_country"][p]["by_gran"]["W"]
        last = w["periods"][-1]
        t = w["by_period"][last]["totals"]
        print(f"  {p} · {len(w['periods'])} semanas · última {last}: "
              + "  ".join(f"{k}={v}" for k, v in t.items() if v))


if __name__ == "__main__":
    if len(sys.argv) != 9:
        print(__doc__)
        sys.exit(1)
    main(*sys.argv[1:])
