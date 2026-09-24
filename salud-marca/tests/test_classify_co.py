"""Verdad de campo: las 4 preguntas de CO, leídas de Ads Manager el 2026-08-31.

Esto no prueba código propio sino que el clasificador siga reproduciendo lo que Meta muestra en
pantalla para un estudio conocido. Es el único ancla contra la deriva: la API no trae etiquetas,
así que si una regla de huella se rompe no hay nada más que lo delate.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import classify_co as CC

HERE = pathlib.Path(__file__).resolve().parents[1]

# Ads Manager → "Habi: Continuous Brand Lift (Jul 2026-Aug 2026)", pestaña por pestaña.
# (control %, expuesto %, lift en pts)
VERDAD_JUL_2026 = {
    "ad_recall":    (25.0, 40.8, +15.8),
    "toma":         (29.1, 41.2, +12.1),
    "favorability": (40.7, 38.3, -2.3),
    "intent":       (17.2, 17.1, -0.1),
}


def _filas_co_jul_2026():
    cache = json.loads((HERE / "brand_lift_cache.json").read_text(encoding="utf-8"))
    return [r for r in cache["rows"] if r["country"] == "CO" and r["month"] == "2026-07"]


def test_el_clasificador_reproduce_las_4_preguntas_de_ads_manager():
    filas = _filas_co_jul_2026()
    assert len(filas) == 4, "el estudio de jul-2026 de CO tiene 4 preguntas"
    mapeo, _ = CC.clasificar(filas)
    por_pregunta = {mapeo[r["experiment_id"]]: r for r in filas if r["experiment_id"] in mapeo}
    assert set(por_pregunta) == set(VERDAD_JUL_2026), "las 4 preguntas quedan mapeadas"
    for q, (control, expuesto, lift) in VERDAD_JUL_2026.items():
        r = por_pregunta[q]
        assert round(100 * r["control"], 1) == control, q
        assert round(100 * r["exposed"], 1) == expuesto, q
        assert round(100 * r["lift"], 1) == lift, q


def test_toma_e_intent_no_se_separan_por_benchmark_sino_por_tasa():
    """Documenta POR QUÉ la regla 3 mira la tasa: por benchmark las dos son casi iguales.
    Si algún día se cambiara a benchmark, este test avisa que no alcanza."""
    filas = _filas_co_jul_2026()
    mapeo, _ = CC.clasificar(filas)
    por_pregunta = {mapeo[r["experiment_id"]]: r for r in filas if r["experiment_id"] in mapeo}
    toma, intent = por_pregunta["toma"], por_pregunta["intent"]
    assert abs(toma["benchmark_region"] - intent["benchmark_region"]) < 0.005
    assert toma["exposed"] - intent["exposed"] > 0.15   # la tasa sí las separa, y con holgura


def test_los_46_estudios_de_co_quedan_mapeados_sin_saltar_ninguno():
    cache = json.loads((HERE / "brand_lift_cache.json").read_text(encoding="utf-8"))
    co = [r for r in cache["rows"] if r["country"] == "CO"]
    mapeo, saltados = CC.clasificar(co)
    assert saltados == []
    assert len(mapeo) == len(co)
