import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_brand_lift as BL

def test_asigna_pregunta_por_experiment_id_conocido():
    rows = [{"experiment_id": "1380313597249074", "question": None,
             "responders_test": 689, "exposed": 0.28}]
    out = BL.map_questions(rows, {"1380313597249074": "ad_recall"})
    assert out[0]["question"] == "ad_recall"

def test_experiment_desconocido_queda_marcado_no_inventado():
    rows = [{"experiment_id": "999", "question": None,
             "responders_test": 500, "exposed": 0.07}]
    out = BL.map_questions(rows, {})
    assert out[0]["question"] == "sin_identificar"

def test_sin_identificar_no_entra_a_la_serie_publicable():
    rows = BL.map_questions([{"experiment_id": "999", "question": None,
                              "responders_test": 500, "exposed": 0.07}], {})
    assert BL.publishable(rows) == []

def test_load_questions_ignora_claves_de_metadata():
    mapping = BL.load_questions()
    assert all(not k.startswith("_") for k in mapping)
