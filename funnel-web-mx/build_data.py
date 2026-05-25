#!/usr/bin/env python3
"""Build funnel-web-mx data.json from 3 BQ query outputs.

Usage:
  python3 build_data.py clicks.json sessions.json leads.json out.json
"""
import json
import sys
from datetime import datetime, timezone
from collections import defaultdict

STAGES = [
    {"id": "click", "label": "Click reportado", "supports": ["canal_plat"]},
    {"id": "session", "label": "Sesion Segment", "supports": ["canal_plat", "device"]},
    {"id": "inicio", "label": "/inicio", "supports": ["canal_plat", "device"]},
    {"id": "zona", "label": "/inmuebles-zona", "supports": ["canal_plat", "device"]},
    {"id": "confirmar_ubicacion", "label": "/confirmar-ubicacion-mx", "supports": ["canal_plat", "device"]},
    {"id": "datos_inmueble", "label": "/datos-inmueble", "supports": ["canal_plat", "device"]},
    {"id": "caracteristicas", "label": "/caracteristicas", "supports": ["canal_plat", "device"]},
    {"id": "ultimos_detalles", "label": "/ultimos-detalles", "supports": ["canal_plat", "device"]},
    {"id": "sugerencias", "label": "/sugerencias-de-propiedades", "supports": ["canal_plat", "device"]},
    {"id": "contacto", "label": "/contacto", "supports": ["canal_plat", "device"]},
    {"id": "felicitaciones", "label": "Form completado (/felicitaciones)", "supports": ["canal_plat", "device"]},
    {"id": "lead", "label": "Lead registrado", "supports": ["canal_plat", "ciudad", "zona_grande", "zona_mediana"]},
]
STAGE_IDS = [s["id"] for s in STAGES]


def new_week():
    return {
        "totals": {sid: 0 for sid in STAGE_IDS},
        "by_canal_plat": defaultdict(lambda: {sid: 0 for sid in STAGE_IDS}),
        "by_device": defaultdict(lambda: {sid: 0 for sid in STAGE_IDS}),
        "by_ciudad": defaultdict(lambda: {sid: 0 for sid in STAGE_IDS}),
        "by_zona_grande": defaultdict(lambda: {sid: 0 for sid in STAGE_IDS}),
        "by_zona_mediana": defaultdict(lambda: {sid: 0 for sid in STAGE_IDS}),
    }


def main(clicks_path, sessions_path, leads_path, out_path):
    clicks = json.load(open(clicks_path))
    sessions = json.load(open(sessions_path))
    leads = json.load(open(leads_path))

    by_week = defaultdict(new_week)

    # CLICKS — stage 'click', only canal_plat
    for r in clicks:
        wk = r["week_start"]
        plat = r["plataforma"]
        cp = f"{plat}/Paid" if plat != "Otro" else "Otro/Otro"
        n = int(r["clicks"])
        by_week[wk]["totals"]["click"] += n
        by_week[wk]["by_canal_plat"][cp]["click"] += n

    # SESSIONS — stages session + 9 form steps, with canal_plat + device
    for r in sessions:
        wk = r["week_start"]
        stage = r["stage"]
        if stage not in STAGE_IDS:
            continue
        cp = r["canal_plat"]
        dev = r["device"]
        n = int(r["n_visitors"])
        by_week[wk]["totals"][stage] += n
        by_week[wk]["by_canal_plat"][cp][stage] += n
        by_week[wk]["by_device"][dev][stage] += n

    # LEADS — stage 'lead', with canal_plat + ciudad + zona_grande + zona_mediana
    for r in leads:
        wk = r["week_start"]
        cp = r["canal_plat"]
        ciudad = r["ciudad"]
        zg = r["zona_grande"]
        zm = r["zona_mediana"]
        n = int(r["n_leads"])
        by_week[wk]["totals"]["lead"] += n
        by_week[wk]["by_canal_plat"][cp]["lead"] += n
        by_week[wk]["by_ciudad"][ciudad]["lead"] += n
        by_week[wk]["by_zona_grande"][zg]["lead"] += n
        by_week[wk]["by_zona_mediana"][zm]["lead"] += n

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "weeks": sorted(by_week.keys()),
        "stages": STAGES,
        "by_week": {
            wk: {
                "totals": w["totals"],
                "by_canal_plat": dict(w["by_canal_plat"]),
                "by_device": dict(w["by_device"]),
                "by_ciudad": dict(w["by_ciudad"]),
                "by_zona_grande": dict(w["by_zona_grande"]),
                "by_zona_mediana": dict(w["by_zona_mediana"]),
            }
            for wk, w in by_week.items()
        },
    }
    with open(out_path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"weeks: {len(out['weeks'])}  range: {out['weeks'][0]} .. {out['weeks'][-1]}")
    print(f"latest totals: {out['by_week'][out['weeks'][-1]]['totals']}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)
    main(*sys.argv[1:])
