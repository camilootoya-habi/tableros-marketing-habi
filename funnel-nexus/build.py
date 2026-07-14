#!/usr/bin/env python3
"""
funnel-nexus/build.py — genera data.json del tablero Funnel Nexus (WEB · sub-fuente Nexus).

Auto-descubierto por scripts/run_queries.py (basta con existir build.py en la carpeta).
Corre query_co.sql y query_mx.sql vía `bq`, agrega a grano diario en dos vistas
(cosecha = fecha de creación, evento = fecha del hito) y escribe data.json.

Cada query devuelve una fila por lead con la fecha (o null) de cada etapa:
  d_reg, d_calif_mm, d_calif_inmo, d_asig, d_cierre_mm, d_captacion_inmo

Aísla fallos por país: si MX falla, CO igual se publica (y viceversa).
"""
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = os.environ.get("GCP_PROJECT", "papyrus-data")
MAX_BYTES = 5_000_000_000

STAGES = ["reg", "calif_mm", "calif_inmo", "asig", "cierre_mm", "captacion_inmo"]
# columna de fecha en la salida de la query -> etapa
DATE_COL = {
    "reg":            "d_reg",
    "calif_mm":       "d_calif_mm",
    "calif_inmo":     "d_calif_inmo",
    "asig":           "d_asig",
    "cierre_mm":      "d_cierre_mm",
    "captacion_inmo": "d_captacion_inmo",
}


def run_query(sql_file: str):
    """Corre una query.sql vía bq y devuelve list[dict]. Levanta si falla."""
    sql = (HERE / sql_file).read_text(encoding="utf-8")
    cmd = [
        "bq", "query", "--nouse_legacy_sql", "--format=json",
        f"--maximum_bytes_billed={MAX_BYTES}", "--max_rows=100000",
        f"--project_id={PROJECT}",
    ]
    out = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:500])
    return json.loads(out.stdout or "[]")


def aggregate(rows):
    """Devuelve (cohort, event): dos dicts {fecha: {stage: count}} a grano diario."""
    cohort = defaultdict(lambda: defaultdict(int))
    event = defaultdict(lambda: defaultdict(int))
    for r in rows:
        d_reg = r.get("d_reg")
        if not d_reg:
            continue
        for stage in STAGES:
            dv = r.get(DATE_COL[stage])
            reached = bool(dv) if stage != "reg" else True
            if reached:
                cohort[d_reg][stage] += 1          # atribuido al periodo de registro
                ev_date = d_reg if stage == "reg" else dv
                event[ev_date][stage] += 1          # atribuido a la fecha del hito
    return cohort, event


def to_rows(agg):
    """dict {fecha:{stage:n}} -> lista ordenada de filas planas por día."""
    out = []
    for d in sorted(agg):
        row = {"d": d}
        for stage in STAGES:
            row[stage] = agg[d].get(stage, 0)
        out.append(row)
    return out


def recent_leads(rows, days=7):
    """Leads creados en los últimos `days` días, más nuevo primero.
    Cada item: nid, created (str), fecha de registro y flags de etapa alcanzada."""
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    out = []
    for r in rows:
        created = (r.get("created") or "")[:16]  # 'YYYY-MM-DD HH:MM'
        d_reg = r.get("d_reg") or ""
        # ventana por fecha de creación (o registro si falta created)
        ref = (created[:10] or d_reg)
        if ref < cutoff:
            continue
        out.append({
            "nid": r.get("nid"),
            "agent": r.get("nexus_agent") or "",
            "created": created,
            "d_reg": d_reg,
            "calif_mm": bool(r.get("d_calif_mm")),
            "calif_inmo": bool(r.get("d_calif_inmo")),
            "asig": bool(r.get("d_asig")),
            "cierre_mm": bool(r.get("d_cierre_mm")),
        })
    out.sort(key=lambda x: (x["created"] or x["d_reg"]), reverse=True)
    return out


def main():
    paises = {"CO": "query_co.sql", "MX": "query_mx.sql"}
    cohort_out, event_out, recent_out = {}, {}, {}
    errors = {}
    for pais, sql_file in paises.items():
        try:
            rows = run_query(sql_file)
            cohort, event = aggregate(rows)
            cohort_out[pais] = to_rows(cohort)
            event_out[pais] = to_rows(event)
            recent_out[pais] = recent_leads(rows, days=7)
            print(f"  ✓ {pais}: {len(rows)} leads · {len(cohort_out[pais])} días · {len(recent_out[pais])} recientes", file=sys.stderr)
        except Exception as e:
            errors[pais] = str(e)
            cohort_out[pais] = []
            event_out[pais] = []
            recent_out[pais] = []
            print(f"  ✗ {pais}: {e}", file=sys.stderr)

    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "paises": ["CO", "MX"],
        "stages": STAGES,
        "cohort": cohort_out,
        "event": event_out,
        "recent": recent_out,
    }
    (HERE / "data.json").write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8"
    )
    if errors and all(not v for v in cohort_out.values()):
        # ambos países fallaron -> error duro para que el cron lo marque
        raise SystemExit(f"build.py falló para todos los países: {errors}")
    print(f"wrote data.json · CO={len(cohort_out['CO'])}d MX={len(cohort_out['MX'])}d", file=sys.stderr)


if __name__ == "__main__":
    main()
