"""El clasificador de MX contra las etiquetas ya guardadas en questions.json.

Las de 2022-2026 se validaron a mano (48 contra Ads Manager en jun-2026, el resto con las mismas
reglas). Si una regla se rompe, este test lo delata antes de que el build mapee mal un mes nuevo.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import classify_mx as CM
import sources_brand_lift as BL

HERE = pathlib.Path(__file__).resolve().parents[1]


def _mx():
    cache = json.loads((HERE / "brand_lift_cache.json").read_text(encoding="utf-8"))
    return [r for r in cache["rows"] if r["country"] == "MX"]


def test_reproduce_todas_las_etiquetas_guardadas_de_mx():
    guardadas = BL.load_questions()
    mapeo, _ = CM.clasificar(_mx())
    comunes = {k for k in mapeo if k in guardadas}
    assert len(comunes) >= 90, "debería cubrir casi toda la historia de MX"
    distintas = {k: (guardadas[k], mapeo[k]) for k in comunes if guardadas[k] != mapeo[k]}
    assert distintas == {}


def test_no_hay_intent_en_mx():
    mapeo, _ = CM.clasificar(_mx())
    assert "intent" not in set(mapeo.values())


def _estudio(sid, filas):
    return [{"country": "MX", "study_id": sid, "experiment_id": e, "exposed": x,
             "responders_test": n, "responders_control": n, "benchmark_region": b}
            for e, x, n, b in filas]


def test_auto_map_solo_toca_estudios_nuevos(tmp_path):
    q = tmp_path / "questions.json"
    q.write_text(json.dumps({"_nota": "x", "viejo1": "ad_recall"}), encoding="utf-8")
    rows = (_estudio("s_viejo", [("viejo1", .3, 500, .05), ("viejo2", .2, 500, .02), ("viejo3", .25, 800, .01)])
            + _estudio("s_nuevo", [("a", .33, 500, .05), ("b", .22, 500, .02), ("c", .26, 800, .01)]))
    nuevos, saltados = BL.auto_map(rows, "MX", path=str(q))
    assert nuevos == {"a": "ad_recall", "b": "toma", "c": "favorability"}
    guardado = json.loads(q.read_text(encoding="utf-8"))
    assert guardado["viejo1"] == "ad_recall" and "viejo2" not in guardado
    assert guardado["_nota"] == "x"


def test_auto_map_no_adivina_si_las_senales_de_favorability_no_coinciden(tmp_path):
    q = tmp_path / "questions.json"
    q.write_text("{}", encoding="utf-8")
    # La de más responders NO es la de benchmark más bajo → se deja sin mapear.
    rows = _estudio("s", [("a", .33, 900, .05), ("b", .22, 500, .02), ("c", .26, 500, .01)])
    nuevos, saltados = BL.auto_map(rows, "MX", path=str(q))
    assert nuevos == {} and saltados and "no coinciden" in saltados[0][1]
    assert json.loads(q.read_text(encoding="utf-8")) == {}
