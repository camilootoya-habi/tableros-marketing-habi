#!/usr/bin/env python3
"""Escribe marketing-loop/cierres.json: cierres y captaciones por mes de la cohorte del loop.

Vive APARTE de build_data.py a propósito: la query escanea ~9,3 GB y build_data.py corre cada 10
minutos (serían ~1,3 TB/día). Este script lo corre update-loop-cierres.yml una vez al día.

Falla RUIDOSAMENTE (exit != 0) si BigQuery da error. Un fallo silencioso aquí es indistinguible de
"no hubo cierres este mes", que es justo el bug que dejó el tablero congelado dos días sin avisar.

Uso: python3 build_cierres.py   (requiere bq autenticado)
"""
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Los papyrus-* ya no aceptan bigquery.jobs.create; el facturador tiene que ser sellers-main-prod.
BQ_PROJECT = os.environ.get("BQ_BILLING_PROJECT", "sellers-main-prod")
# La query escanea ~9,3 GB. El tope corta una regresión de costo antes de que llegue a la factura.
MAX_BYTES = 15_000_000_000


def run_query():
    sql = open(os.path.join(HERE, "query_cierres_captaciones.sql"), encoding="utf-8").read()
    out = subprocess.run(
        ["bq", f"--project_id={BQ_PROJECT}", "query", "--use_legacy_sql=false",
         "--format=json", "--max_rows=10000", f"--maximum_bytes_billed={MAX_BYTES}"],
        input=sql, capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        sys.exit(f"bq falló (rc={out.returncode}): {out.stderr.strip()[:600]}")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError as e:
        sys.exit(f"bq devolvió algo que no es JSON ({e}): {out.stdout[:300]}")


def eje_meses(desde, hasta):
    """Meses consecutivos de `desde` a `hasta` inclusive, ambos 'YYYY-MM'.

    El gráfico necesita el eje completo: un mes sin ningún evento tiene que salir en cero, no
    desaparecer, o la serie miente sobre la continuidad.
    """
    y, m = int(desde[:4]), int(desde[5:7])
    fin = (int(hasta[:4]), int(hasta[5:7]))
    out = []
    while (y, m) <= fin:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def main():
    raw = run_query()
    if not raw:
        sys.exit("la query no devolvió filas: la cohorte del loop no cruzó con ninguna tabla de funnel")

    ts = os.environ.get("BUILD_TS") or datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    idx = {(r["mes"], r["pais"]): r for r in raw}
    meses = eje_meses(min(r["mes"] for r in raw), ts[:7])

    rows = [{"mes": mes, "pais": pais,
             "captaciones": int(idx.get((mes, pais), {}).get("captaciones") or 0),
             "cierres": int(idx.get((mes, pais), {}).get("cierres") or 0)}
            for mes in meses for pais in ("CO", "MX")]

    path = os.path.join(HERE, "cierres.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"updated": ts, "rows": rows}, fh, ensure_ascii=False, separators=(",", ":"))

    resumen = " | ".join(
        f"{p} captaciones={sum(r['captaciones'] for r in rows if r['pais'] == p)}"
        f" cierres={sum(r['cierres'] for r in rows if r['pais'] == p)}"
        for p in ("CO", "MX"))
    print(f"cierres.json OK | {len(meses)} meses ({meses[0]}→{meses[-1]}) | {resumen}")


if __name__ == "__main__":
    main()
