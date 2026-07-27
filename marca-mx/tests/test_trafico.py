import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_bq

def test_cpv_es_spend_sobre_usuarios():
    s = sources_bq.traffic_series([
        {"month": "2026-07", "plaza": "MTY", "users": "10000", "spend": "343635.0"}])
    assert s[0]["users"] == 10000
    assert round(s[0]["cpv"], 4) == 34.3635

def test_sin_inversion_el_cpv_es_none_no_cero():
    s = sources_bq.traffic_series([
        {"month": "2026-07", "plaza": "Resto", "users": "500", "spend": None}])
    assert s[0]["spend"] is None
    assert s[0]["cpv"] is None       # un CPV de 0 mentiría: no hubo medición, no hubo gasto cero

def test_usuarios_en_cero_no_divide_por_cero():
    s = sources_bq.traffic_series([
        {"month": "2026-07", "plaza": "GDL", "users": "0", "spend": "100.0"}])
    assert s[0]["cpv"] is None
