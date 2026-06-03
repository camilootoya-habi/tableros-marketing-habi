#!/usr/bin/env python3
"""
Builds mapa-leads-zonas/data.json from BQ query output (CO + MX).

Usage:
  build_data.py <bq_query_output.json> <output_data.json>

Input rows (col `kind`):
  geo:   {"kind":"geo",   "pais","mes","fuente","lat","lng","reg","calif","asig","cierre"}
  nogeo: {"kind":"nogeo", "pais","mes","fuente","reg","calif","asig","cierre"}  (lat/lng null)

Output (compact array-of-arrays):
  {
    "generated": ISO8601,
    "window_months": 12,
    "fuentes": [str, ...],          # index -> fuente
    "meses":   ["YYYY-MM", ...],    # index -> month (sorted asc, by fecha_creacion)
    "rows":    [[paisIdx, mesIdx, fuenteIdx, lat, lng, reg, calif, asig, cierre], ...]  # geolocalizados
    "nogeo":   [[paisIdx, mesIdx, fuenteIdx, reg, calif, asig, cierre], ...]            # sin coordenadas
                # paisIdx: 0=CO, 1=MX. Cohorte por mes de creación.
  }
"""
import json
import sys
from datetime import datetime, timezone

PAIS_IDX = {"CO": 0, "MX": 1}


def main():
    if len(sys.argv) != 3:
        print("Usage: build_data.py <bq_query_output.json> <output_data.json>", file=sys.stderr)
        sys.exit(1)
    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    fuentes, meses = [], []
    fuente_idx, mes_idx = {}, {}

    def f_id(name):
        if name not in fuente_idx:
            fuente_idx[name] = len(fuentes)
            fuentes.append(name)
        return fuente_idx[name]

    def m_id(name):
        if name not in mes_idx:
            mes_idx[name] = len(meses)
            meses.append(name)
        return mes_idx[name]

    for m in sorted({r["mes"] for r in raw}):
        m_id(m)

    rows, nogeo = [], []
    for r in raw:
        base = [PAIS_IDX[r["pais"]], m_id(r["mes"]), f_id(r["fuente"] or "Otro")]
        if r["kind"] == "geo":
            rows.append(base + [round(float(r["lat"]), 4), round(float(r["lng"]), 4),
                                int(r["reg"]), int(r["calif"]), int(r["asig"]), int(r["cierre"])])
        else:
            nogeo.append(base + [int(r["reg"]), int(r["calif"]), int(r["asig"]), int(r["cierre"])])

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "window_months": 12,
        "fuentes": fuentes,
        "meses": meses,
        "rows": rows,
        "nogeo": nogeo,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)

    greg = sum(r[5] for r in rows)
    nreg = sum(r[3] for r in nogeo)
    print(f"wrote {out_path}: {len(rows)} geo rows ({greg} reg) | "
          f"{len(nogeo)} nogeo rows ({nreg} reg) | "
          f"{len(fuentes)} fuentes, {len(meses)} meses", file=sys.stderr)


if __name__ == "__main__":
    main()
