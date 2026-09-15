"""Mapea `experiment_id` → pregunta para CO por huella de benchmark, y escribe questions.json.

Se corre A MANO cuando entra un estudio nuevo, nunca desde el cron: es una decisión de
identificación, no un refresco de datos.

Mapea las 4 preguntas de CO. Las cuatro reglas se validaron contra Ads Manager el 2026-08-31
sobre el estudio "Jul 2026-Aug 2026", y las cuatro coinciden al decimal:
Ad recall 25.0→40.8 (+15.8) · Top of mind 29.1→41.2 (+12.1) · Brand favorability 40.7→38.3
(−2.3) · Intent 17.2→17.1 (−0.1).

Reglas, dentro de UN estudio (nunca dentro de un mes: dos estudios pueden caer en el mismo mes
calendario, ver `study_month`):
  1. favorability = la de MÁS responders (~2x) que además tenga el `benchmark_region` MÁS BAJO.
     Dos señales independientes; si no coinciden, el estudio se deja sin mapear.
  2. ad_recall = `benchmark_region` MÁS ALTO de las restantes, con margen ≥1.5 pts sobre la
     siguiente. El benchmark de ad_recall vive en 4-6 y el resto abajo de 2.
  3. De las dos que sobran, toma = la de MAYOR tasa de expuestos e intent = la menor. NO se usa
     el benchmark: TOMA e Intent lo tienen casi idéntico (0.40 vs 0.69 pts de distancia al TOMA
     de MX) y por ahí no se separan. La tasa sí: en los 46 estudios los rangos jamás se solapan
     —27.7-53.8% contra 9.1-18.6%—. Ojo con la intuición de comparar contra MX: el TOMA de CO da
     más alto porque elige entre 3 marcas y el de MX entre 4, así que el rango de MX (11-20%) se
     parece al de Intent de CO por coincidencia. El separador honesto es la tasa dentro del
     estudio, no el parecido con el otro país.
"""
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
MARGEN_AD_RECALL = 0.015   # 1.5 pts en fracción


def clasificar(rows):
    """→ ({experiment_id: pregunta}, [(study_id, motivo) sin mapear])"""
    por_estudio = defaultdict(list)
    for r in rows:
        por_estudio[r["study_id"]].append(r)

    mapeo, saltados = {}, []
    for sid, rs in sorted(por_estudio.items()):
        if len(rs) < 3:
            saltados.append((sid, f"solo {len(rs)} preguntas"))
            continue
        resp = lambda r: (r.get("responders_test") or 0) + (r.get("responders_control") or 0)
        bmr = lambda r: r.get("benchmark_region") or 0

        f_resp, f_bm = max(rs, key=resp), min(rs, key=bmr)
        if f_resp["experiment_id"] != f_bm["experiment_id"]:
            saltados.append((sid, "favorability: las dos señales no coinciden"))
            continue
        mapeo[f_resp["experiment_id"]] = "favorability"

        resto = sorted((r for r in rs if r is not f_resp), key=bmr, reverse=True)
        margen = bmr(resto[0]) - bmr(resto[1]) if len(resto) > 1 else 1
        if margen < MARGEN_AD_RECALL:
            saltados.append((sid, f"ad_recall sin margen: {100*margen:.2f} pts"))
            continue
        mapeo[resto[0]["experiment_id"]] = "ad_recall"

        ultimas = sorted(resto[1:], key=lambda r: -(r.get("exposed") or 0))
        if len(ultimas) == 2:
            mapeo[ultimas[0]["experiment_id"]] = "toma"
            mapeo[ultimas[1]["experiment_id"]] = "intent"
        elif ultimas:
            # Un estudio con 3 preguntas no permite decir si la que sobra es TOMA o Intent.
            saltados.append((sid, "queda 1 pregunta sola: no se puede decir si es toma o intent"))
    return mapeo, saltados


def main():
    cache = json.load(open(os.path.join(HERE, "brand_lift_cache.json"), encoding="utf-8"))
    co = [r for r in cache["rows"] if r.get("country") == "CO"]
    mapeo, saltados = clasificar(co)

    ruta = os.path.join(HERE, "questions.json")
    actual = json.load(open(ruta, encoding="utf-8"))
    nuevos = {k: v for k, v in mapeo.items() if k not in actual}
    conflictos = {k: (actual[k], v) for k, v in mapeo.items()
                  if k in actual and actual[k] != v}
    if conflictos:
        print("ABORTA — el clasificador contradice un mapeo ya guardado:")
        for k, (viejo, nuevo) in conflictos.items():
            print(f"  {k}: guardado={viejo} clasificador={nuevo}")
        return 1

    actual.update(nuevos)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(actual, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"CO: {len(mapeo)} ids mapeados ({len(nuevos)} nuevos) sobre "
          f"{len({r['study_id'] for r in co})} estudios")
    if saltados:
        print(f"estudios sin mapear: {len(saltados)}")
        for sid, m in saltados:
            print(f"  {sid}: {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
