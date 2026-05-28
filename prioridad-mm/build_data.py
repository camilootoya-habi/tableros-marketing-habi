#!/usr/bin/env python3
"""Reshape BQ output into compact data.json for prioridad-mm dashboard.

Input rows: semana, country, fuente, area, asignado (bool), a, b, c, sin_tip, n.
Output (granular, cliente filtra y suma):
{
  "updated_at": "...",
  "weeks": ["2026-01-19", ...],
  "min_n_area_threshold": 100,
  "countries": {
    "Colombia": {
      "fuentes": ["Todas", "web", "estudio inmueble", "crm", ...],
      "areas":   ["Todas", "Bogotá", "Valle de Aburrá", ...],
      "rows": [
        {"w": 0, "f": "web", "ar": "Bogotá", "as": 1, "a": 12, "b": 8, "c": 4, "s": 30, "n": 54},
        ...
      ]
    },
    "México": { ... }
  }
}

w = índice en weeks. f = fuente. ar = área (con "Otras" para áreas con n total < umbral). as = 1/0 (asignado).
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

MIN_N_AREA = 100

if len(sys.argv) != 3:
    print("Usage: build_data.py <bq_raw.json> <out_path>", file=sys.stderr)
    sys.exit(1)

with open(sys.argv[1]) as f:
    raw = json.load(f)

weeks = sorted({r["semana"] for r in raw})
week_idx = {w: i for i, w in enumerate(weeks)}
countries = ("Colombia", "México")

def normalize_area(a: str) -> str:
    if not a or a.lower() == "not found":
        return "Sin clasificar"
    return a

# Total por (country, area) para decidir cuáles caen a 'Otras'
area_totals = defaultdict(int)
for r in raw:
    area = normalize_area(r["area"])
    area_totals[(r["country"], area)] += int(r["n"])

def bucket_area(country: str, area: str) -> str:
    area = normalize_area(area)
    return area if area_totals[(country, area)] >= MIN_N_AREA else "Otras"

# Acumulador: (country, w, fuente, area_bucket, asignado) -> {a,b,c,s,n}
acc = defaultdict(lambda: {"a": 0, "b": 0, "c": 0, "s": 0, "n": 0})
for r in raw:
    key = (
        r["country"],
        week_idx[r["semana"]],
        r["fuente"],
        bucket_area(r["country"], r["area"]),
        1 if r["asignado"] in ("true", True) else 0,
    )
    acc[key]["a"] += int(r["a"])
    acc[key]["b"] += int(r["b"])
    acc[key]["c"] += int(r["c"])
    acc[key]["s"] += int(r["sin_tip"])
    acc[key]["n"] += int(r["n"])

# Totales por país para ordenar dropdowns
fuente_totals = defaultdict(int)
area_bucket_totals = defaultdict(int)
for (country, w, fuente, area, asig), cells in acc.items():
    fuente_totals[(country, fuente)] += cells["n"]
    area_bucket_totals[(country, area)] += cells["n"]

out = {
    "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "weeks": weeks,
    "min_n_area_threshold": MIN_N_AREA,
    "countries": {},
}

for country in countries:
    fuentes = sorted(
        {f for (c, f) in fuente_totals if c == country},
        key=lambda f: fuente_totals[(country, f)],
        reverse=True,
    )
    areas = sorted(
        {a for (c, a) in area_bucket_totals if c == country},
        key=lambda a: area_bucket_totals[(country, a)],
        reverse=True,
    )
    # 'Otras' al final si está
    if "Otras" in areas:
        areas.remove("Otras"); areas.append("Otras")

    rows = []
    for (c, w, f, ar, asig), cells in acc.items():
        if c != country:
            continue
        rows.append({
            "w": w, "f": f, "ar": ar, "as": asig,
            "a": cells["a"], "b": cells["b"], "c": cells["c"],
            "s": cells["s"], "n": cells["n"],
        })

    out["countries"][country] = {
        "fuentes": ["Todas"] + fuentes,
        "areas": ["Todas"] + areas,
        "rows": rows,
    }

with open(sys.argv[2], "w") as f:
    json.dump(out, f, separators=(",", ":"), ensure_ascii=False)

print(f"Weeks: {len(weeks)} | Countries: {list(out['countries'].keys())}")
for c in countries:
    cdata = out["countries"][c]
    print(f"  {c}: fuentes={len(cdata['fuentes'])-1}, areas={len(cdata['areas'])-1}, rows={len(cdata['rows'])}")
