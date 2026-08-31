import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import contract

def test_metric_ok_lleva_source_y_serie():
    m = contract.metric("ok", source="bq", series=[{"month": "2026-07"}])
    assert m["status"] == "ok" and m["source"] == "bq" and len(m["series"]) == 1
    assert "reason" not in m

def test_metric_not_available_exige_razon_y_no_trae_serie_en_cero():
    m = contract.metric("not_available", reason="Sin export de GA4 usable para CO.")
    assert m["status"] == "not_available"
    assert m["reason"].endswith(".")
    assert m.get("series") in (None, [])   # jamás una serie de ceros

def test_metric_not_available_sin_razon_es_error():
    try:
        contract.metric("not_available")
    except ValueError as e:
        assert "reason" in str(e)
    else:
        raise AssertionError("debió exigir reason")

def test_envelope_arma_las_tres_metricas_por_pais():
    env = contract.envelope({"brand_lift": {"MX": contract.metric("ok", source="api", series=[])}},
                            now="2026-07-27T18:00:00Z")
    assert env["generated_at"] == "2026-07-27T18:00:00Z"
    assert env["metrics"]["brand_lift"]["MX"]["status"] == "ok"

def test_metric_stale_conserva_serie_y_last_updated():
    m = contract.metric("stale", series=[{"month": "2026-06"}, {"month": "2026-07"}], last_updated="2026-07-24T12:00:00Z")
    assert m["status"] == "stale"
    assert len(m["series"]) == 2
    assert m["last_updated"] == "2026-07-24T12:00:00Z"
    assert "reason" not in m


def test_planned_marca_lo_que_no_existe_todavia():
    """Un indicador planeado y una fuente sin conectar son los dos `not_available`, pero el
    lector necesita distinguirlos: uno espera trabajo técnico, el otro espera una decisión."""
    m = contract.metric("not_available", reason="el agente no existe", planned=True)
    assert m["planned"] is True and m["status"] == "not_available"


def test_planned_no_aplica_a_una_metrica_con_datos():
    import pytest
    with pytest.raises(ValueError):
        contract.metric("ok", series=[], planned=True)


def test_planned_sigue_exigiendo_razon():
    import pytest
    with pytest.raises(ValueError):
        contract.metric("not_available", planned=True)
