#!/usr/bin/env python3
"""
Builds mapa-leads-zonas/zonas-co.json (GeoJSON FeatureCollection) from BQ output.

Usage:
  build_zonas.py <bq_query_output.json> <output_geojson.json>

Input rows: {"zid", "zona", "activo", "npts", "geojson": "<Polygon GeoJSON string>"}
Output: GeoJSON FeatureCollection; props per feature: {zid, zona, activo} (activo 1=abierta).
"""
import json
import sys


def main():
    if len(sys.argv) != 3:
        print("Usage: build_zonas.py <in.json> <out.json>", file=sys.stderr)
        sys.exit(1)
    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    feats = []
    for r in raw:
        gj = r.get("geojson")
        if not gj:
            continue
        try:
            geom = json.loads(gj)
        except (TypeError, ValueError):
            continue
        feats.append({
            "type": "Feature",
            "properties": {
                "zid": int(r["zid"]),
                "zona": r.get("zona") or f"Zona {r['zid']}",
                "activo": int(r["activo"]),
            },
            "geometry": geom,
        })

    out = {"type": "FeatureCollection", "features": feats}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)

    act = sum(1 for x in feats if x["properties"]["activo"] == 1)
    print(f"wrote {out_path}: {len(feats)} zonas ({act} abiertas, {len(feats)-act} cerradas)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
