from sources_infobip import map_log
from agg import err_bucket

def test_map_delivered():
    r={"messageId":"m1","status":{"groupName":"DELIVERED"},"error":{"id":0,"name":"NO_ERROR"}}
    assert map_log(r)=={"status":"delivered","error_name":"No Error (code 0)","seen":False}
    assert err_bucket(map_log(r)["error_name"])=="entregado"

def test_map_freqcap():
    r={"messageId":"m2","status":{"groupName":"UNDELIVERABLE"},"error":{"id":7032,"name":"EC_FREQUENCY_CAPPING"}}
    m=map_log(r)
    assert m["status"]=="undeliverable"
    assert "7032" in m["error_name"]
    assert err_bucket(m["error_name"])=="freq_cap"

def test_map_no_error_key():
    r={"messageId":"m3","status":{"groupName":"PENDING"}}
    assert map_log(r)["error_name"]=="No Error (code 0)"
    assert map_log(r)["status"]=="pending"
