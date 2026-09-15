"""Siembra `brand_lift_cache.json` a partir del backfill histórico ya corrido a mano.

El backfill supervisado (ver spec, "Reglas de trato con la cuenta publicitaria") paginó
`act_205661715114408` (MX) y `act_770068953990542` (CO) una sola vez, fuera del cron, y dejó su
salida en un JSON con el esquema crudo de la API (`cell_id`, `objective_id`, `objective_type`,
`start_time`, sin `month` ni `question`). Este script la transforma al esquema que produce
`sources_brand_lift.parse_results` / consume `load_cache`, sin volver a llamar a Meta.

No filtra ni deduplica: preserva cada fila del backfill tal cual. Se corre una sola vez; queda
commiteado para documentar cómo se construyó el caché versionado.

Uso:
    python3 seed_cache.py [ruta/al/backfill/crudo.json]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOURCE = ("/tmp/claude-1000/-home-administrador/"
                   "d36d6067-801d-4aa5-a011-ed42758c79a2/scratchpad/brand_lift_cache.json")
TARGET = os.path.join(HERE, "brand_lift_cache.json")

# Mismas llaves, mismo orden, que emite sources_brand_lift.parse_results.
FIELDS = ("country", "month", "study_id", "study_name", "end_time", "experiment_id",
          "question", "exposed", "control", "lift", "ci_lower", "ci_upper",
          "responders_test", "responders_control", "confidence", "spend",
          "benchmark_region", "benchmark_vertical")


def transform(raw_row):
    row = dict(raw_row)
    row["month"] = raw_row["start_time"][:7]
    row["question"] = None
    return {k: row[k] for k in FIELDS}


def main(source_path):
    with open(source_path, encoding="utf-8") as f:
        raw = json.load(f)
    rows = [transform(r) for r in raw["rows"]]
    with open(TARGET, "w", encoding="utf-8") as f:
        json.dump({"rows": rows}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"sembradas {len(rows)} filas en {TARGET}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE)
