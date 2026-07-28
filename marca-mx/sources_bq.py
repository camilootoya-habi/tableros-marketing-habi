"""Consultas a BigQuery. `bq` por subprocess, patrón de marketing-loop/build_data.py.
bq devuelve todos los números como string: convertir aquí, no en el HTML."""
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

# Marca dónde empieza el texto libre. Ninguna opción del catálogo contiene la palabra "otro".
_OTRO = re.compile(r"\botro\b", re.IGNORECASE)


def opciones_elegidas(valor):
    """El exit poll es de SELECCIÓN MÚLTIPLE: un solo valor guarda todas las opciones marcadas
    separadas por coma ("Televisión, Búsqueda en Google, Vehículos de Uber"), y al final
    "Otro: <texto libre>" cuando la persona escribió algo.

    Dos consecuencias que hay que respetar:

    1. Hay que partir por coma. Contar el valor completo como si fuera una opción convierte cada
       combinación en una categoría propia y produce cientos de series de una sola respuesta.
    2. **El texto libre se descarta.** Trae datos personales — correos y nombres de personas
       aparecieron en los datos reales — y este tablero se publica en GitHub Pages desde un repo
       público. Solo se conserva que la respuesta fue "Otro". Se corta desde la palabra "otro"
       en adelante, no por coma, porque el texto libre puede tener comas dentro.

    Los shares por opción suman más de 100% a propósito: una persona marca varias.
    """
    v = (valor or "").strip().strip('"').strip()
    if not v:
        return []
    m = _OTRO.search(v)
    if m:
        v = v[:m.start()]
    partes = [p.strip().strip('"').strip(" ,") for p in v.split(",")]
    partes = [p for p in partes if p]
    if m:
        partes.append("Otro")
    # dedup preservando orden: "Redes sociales, Redes sociales" no cuenta doble
    vistas, out = set(), []
    for p in partes:
        if p not in vistas:
            vistas.add(p)
            out.append(p)
    return out


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
        elegidas = opciones_elegidas(r.get("opcion"))
        if elegidas:
            a["respuestas"] += n
            for opcion in elegidas:
                a["opciones"][opcion] = a["opciones"].get(opcion, 0) + n
    for a in acc.values():
        a["tasa"] = a["respuestas"] / a["registros_web"] if a["registros_web"] else 0.0
    return [acc[k] for k in sorted(acc)]


def traffic_series(rows):
    """Usuarios activos e inversión por (mes, plaza) → CPV. Sin inversión o sin usuarios,
    cpv=None: un cero se leería como 'costó cero', que es distinto de 'no hay dato'."""
    out = []
    for r in rows:
        users = int(r["users"] or 0)
        spend = float(r["spend"]) if r.get("spend") is not None else None
        out.append({
            "month": r["month"], "plaza": r["plaza"], "users": users, "spend": spend,
            "cpv": (spend / users) if (spend is not None and users) else None,
        })
    return sorted(out, key=lambda x: (x["month"], x["plaza"]))
