"""Consultas a BigQuery. `bq` por subprocess, patrón de marketing-loop/build_data.py.
bq devuelve todos los números como string: convertir aquí, no en el HTML."""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

# Valor de estado_mexico -> plaza. Reflejo del CASE de queries/exit_poll.sql,
# expuesto para quien necesite mapear un estado_mexico sin volver a ejecutar la query.
PLAZA_EXIT_POLL = {
    "Nuevo Leon": "MTY",
    "Nuevo León": "MTY",
    "Jalisco": "GDL",
    "Ciudad de Mexico": "CDMX",
    "Ciudad de México": "CDMX",
    "Distrito Federal": "CDMX",
    "Estado de Mexico": "CDMX",
    "Estado de México": "CDMX",
    "Mexico": "CDMX",
    "México": "CDMX",
}


def run_query(sql_path, max_bytes=20_000_000_000):
    sql = open(os.path.join(HERE, sql_path), encoding="utf-8").read()
    out = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json",
         "--max_rows=100000", f"--maximum_bytes_billed={max_bytes}"],
        input=sql, capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        raise RuntimeError(f"bq falló en {sql_path}: {out.stderr.strip()[:400]}")
    return json.loads(out.stdout or "[]")


def exit_poll_series(rows):
    """Agrupa (mes, plaza): registros WEB totales, respuestas, tasa y conteo por opción."""
    acc = {}
    for r in rows:
        k = (r["month"], r["plaza"])
        a = acc.setdefault(k, {"month": r["month"], "plaza": r["plaza"],
                               "registros_web": 0, "respuestas": 0, "opciones": {}})
        n = int(r["registros_web"])
        a["registros_web"] += n
        opcion = (r.get("opcion") or "").strip()
        if opcion:
            a["respuestas"] += n
            a["opciones"][opcion] = a["opciones"].get(opcion, 0) + n
    for a in acc.values():
        a["tasa"] = a["respuestas"] / a["registros_web"] if a["registros_web"] else 0.0
    return [acc[k] for k in sorted(acc)]
