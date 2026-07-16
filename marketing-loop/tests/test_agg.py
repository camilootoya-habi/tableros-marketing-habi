from agg import bucket, parse_resp

def test_bucket_dia():
    assert bucket("2026-07-15", "dia") == "2026-07-15"

def test_bucket_mes():
    assert bucket("2026-07-15", "mes") == "2026-07-01"

def test_bucket_semana():
    assert bucket("2026-07-15", "semana") == "2026-07-13"  # lunes

def test_parse_interesado():
    r = parse_resp("BUTTON - Text: Estoy interesado, Payload: activacion_NewLeads_INTERESADO_123")
    assert r == {"action": "INTERESADO", "nid": "123"}

def test_parse_baja():
    r = parse_resp("BUTTON - Text: Darme de baja, Payload: activacion_NewLeads_YAVENDIÓ_9")
    assert r["action"] == "YAVENDIO" and r["nid"] == "9"

def test_parse_libre():
    assert parse_resp("Hola quiero info") == {"action": "OTRO", "nid": None}

def test_bucket_ciclo():
    # ciclo = miércoles de la semana comercial (Mié→Mar). 2026-07-16 es jueves → miércoles 2026-07-15
    assert bucket("2026-07-16", "ciclo") == "2026-07-15"
    assert bucket("2026-07-14", "ciclo") == "2026-07-08"  # martes → miércoles previo

def test_parse_yavendio_sin_acento():
    r = parse_resp("BUTTON - Text: Ya no vendo, Payload: activacion_NewLeads_YAVENDIO_777")
    assert r == {"action": "YAVENDIO", "nid": "777"}

def test_parse_case_insensitive():
    r = parse_resp("payload: activacion_newleads_interesado_123")
    assert r == {"action": "INTERESADO", "nid": "123"}
