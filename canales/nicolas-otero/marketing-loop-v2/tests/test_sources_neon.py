import sources_neon as N
import agg

def test_delivery_dict_with_error():
    d = N._delivery_dict("undeliverable", "EC_FREQUENCY_CAPPING", 7032)
    assert d["status"] == "undeliverable"
    assert d["error_name"] == "EC_FREQUENCY_CAPPING (code 7032)"
    assert agg.err_bucket(d["error_name"]) == "freq_cap"

def test_delivery_dict_no_error():
    d = N._delivery_dict("delivered", None, 0)
    assert d["status"] == "delivered" and d["error_name"] == "No Error (code 0)"
    assert agg.err_bucket(d["error_name"]) == "entregado"

def test_delivery_dict_invalido_code_351():
    d = N._delivery_dict("undeliverable", "EC_INVALID_DESTINATION", 351)
    assert agg.err_bucket(d["error_name"]) == "invalido"
