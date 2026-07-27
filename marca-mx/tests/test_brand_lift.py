import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_brand_lift as BL

RESULT = json.dumps({
    "cell_id": "987465497325149", "experiment_id": "1380313597249074",
    "scoreMean.test": 0.28415, "scoreMean.control": 0.33241,
    "scoreMean.incremental": -0.04826, "brandLiftCILower": -0.08962,
    "brandLiftCIUpper": -0.00212, "responders.test": 689, "responders.control": 676,
    "breakthroughs.singleCellBayesianConfidence": 0.05, "spend": 140867.87,
    "scoreMeanRegion": 0.01017, "scoreMeanVertical": None,
})
STUDY = {"id": "2539254759864543", "name": "HABI MX - Continuous Brand Lift (Jul 2026-Jul 2026)",
         "type": "LIFT", "start_time": "2026-07-01T07:00:00+0000",
         "end_time": "2026-08-01T06:59:59+0000",
         "objectives": {"data": [{"id": "1376237287787800", "type": "BRAND",
                                  "results": [RESULT]}]}}

def test_parse_desenvuelve_el_json_anidado_en_string():
    rows = BL.parse_results([STUDY], "MX")
    assert len(rows) == 1
    r = rows[0]
    assert r["country"] == "MX" and r["month"] == "2026-07"
    assert round(r["exposed"], 5) == 0.28415
    assert round(r["lift"], 5) == -0.04826
    assert r["experiment_id"] == "1380313597249074"

def test_resultado_sin_experiment_id_se_descarta():
    s = dict(STUDY)
    s["objectives"] = {"data": [{"id": "x", "type": "BRAND",
                                 "results": [json.dumps({"cell_id": "1"})]}]}
    assert BL.parse_results([s], "MX") == []

def test_estudio_no_lift_se_ignora():
    s = dict(STUDY, type="SPLIT_TEST_V2")
    assert BL.parse_results([s], "MX") == []

def test_series_agrupa_por_mes_y_pregunta():
    rows = BL.parse_results([STUDY], "MX")
    rows[0]["question"] = "ad_recall"
    s = BL.series(rows)
    assert s[0]["month"] == "2026-07" and s[0]["question"] == "ad_recall"
