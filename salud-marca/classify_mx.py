"""Mapea `experiment_id` → pregunta para MX por huella de benchmark. Hermano de classify_co.py.

Las reglas son las del campo `_nota` de questions.json, validadas en jun-2026 contra 48
etiquetas leídas en Ads Manager (16 meses × 3 preguntas). Dentro de UN estudio:
  1. favorability = la de MÁS responders que además tenga el `benchmark_region` MÁS BAJO. Dos
     señales independientes; si no coinciden, el estudio se deja sin mapear.
  2. ad_recall = `benchmark_region` MÁS ALTO de las restantes.
  3. toma = la de mayor tasa de expuestos entre las que sobran. Con 3 preguntas (desde 2025-04)
     es la única que queda. Con 4 (antes de 2024-05) la cuarta, de base baja, queda sin mapear
     a propósito: nadie confirmó su nombre.

No hay Intent en MX.
"""
from collections import defaultdict


def clasificar(rows):
    """→ ({experiment_id: pregunta}, [(study_id, motivo) sin mapear])"""
    por_estudio = defaultdict(list)
    for r in rows:
        por_estudio[r["study_id"]].append(r)

    resp = lambda r: (r.get("responders_test") or 0) + (r.get("responders_control") or 0)
    bmr = lambda r: r.get("benchmark_region") or 0

    mapeo, saltados = {}, []
    for sid, rs in sorted(por_estudio.items()):
        if len(rs) not in (3, 4):
            saltados.append((sid, f"{len(rs)} preguntas"))
            continue
        f_resp, f_bm = max(rs, key=resp), min(rs, key=bmr)
        if f_resp["experiment_id"] != f_bm["experiment_id"]:
            saltados.append((sid, "favorability: las dos señales no coinciden"))
            continue
        resto = sorted((r for r in rs if r is not f_resp), key=bmr, reverse=True)
        ultimas = sorted(resto[1:], key=lambda r: -(r.get("exposed") or 0))
        mapeo[f_resp["experiment_id"]] = "favorability"
        mapeo[resto[0]["experiment_id"]] = "ad_recall"
        mapeo[ultimas[0]["experiment_id"]] = "toma"
    return mapeo, saltados
