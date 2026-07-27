from agg import bucket, parse_resp, embudo, err_bucket, errores_por_tipo, cohorte, recreacion_serie, antifunnel_serie, contact_dist

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

def test_embudo_tasas():
    sl=[{"message_id":"a","accepted":True,"phone":"1","attempted_at":"2026-07-10","nid":"n1"},
        {"message_id":"b","accepted":True,"phone":"2","attempted_at":"2026-07-10","nid":"n2"},
        {"message_id":None,"accepted":False,"phone":"3","attempted_at":"2026-07-10","nid":"n3"}]
    mart={"a":{"status":"delivered","error_name":"No Error (code 0)","seen":True},
          "b":{"status":"undeliverable","error_name":"Frequency capping limit reached (code 7032)","seen":False}}
    r=embudo(sl, mart, inbound_phones={"1"}, interesado_phones={"1"},
             recreated_oldnids={"n1"}, qualified_oldnids={"n1"}, dias=["2026-07-10"])
    t=r["totales"]
    assert t["intentos"]==3 and t["aceptados"]==2 and t["entregados"]==1 and t["leidos"]==1
    assert t["respondieron"]==1 and t["interesados"]==1 and t["recreados"]==1 and t["calificados"]==1
    assert round(r["tasas"]["delivery_rate"],2)==0.33 and round(r["tasas"]["respond_rate"],2)==1.0

def test_embudo_rellena_ceros_y_totales_acotados():
    sl=[{"message_id":"a","accepted":True,"phone":"1","attempted_at":"2026-07-10","nid":"n1"}]
    mart={"a":{"status":"delivered","error_name":"No Error (code 0)","seen":True}}
    r=embudo(sl, mart, inbound_phones=set(), interesado_phones=set(),
             recreated_oldnids=set(), qualified_oldnids=set(), dias=["2026-07-10","2026-07-11"])
    assert len(r["serie"])==2                     # rellena el día sin actividad
    assert r["serie"][1]["fecha"]=="2026-07-11" and r["serie"][1]["intentos"]==0
    assert r["totales"]["intentos"]==1 and r["tasas"]["send_rate"]==1.0

def test_err_bucket():
    assert err_bucket("Frequency capping limit reached (code 7032)")=="freq_cap"
    assert err_bucket("User device was not able to reproduce the content (code 7020)")=="device_error"
    assert err_bucket("No Error (code 0)")=="entregado"

def test_cohorte():
    sl=[{"message_id":"a","nid":"n1"},{"message_id":"b","nid":"n2"}]
    mart={"a":{"error_name":"No Error (code 0)"},"b":{"error_name":"...(code 7020)"}}
    q={"n1":"2024-Q1","n2":"2024-Q1"}
    r=cohorte(sl,mart,q)
    assert r[0]["bucket"]=="2024-Q1" and r[0]["enviados"]==2 and r[0]["device_error"]==1 and r[0]["entregados"]==1

def test_recreacion():
    # duplicado = estado_id "1"; calificado = calif "1" (estado 20/63). Fuente: query_recreados.
    rr=[{"fecha_creacion":"2026-07-14","estado_id":"1","calif":"0"},
        {"fecha_creacion":"2026-07-14","estado_id":"20","calif":"1"}]
    r=recreacion_serie(rr,"dia")
    assert r[0]=={"bucket":"2026-07-14","recreados":2,"duplicado":1,"calificado":1}

def test_antifunnel_serie():
    rr=[{"fecha_creacion":"2026-07-14","estado_label":"Duplicado"},
        {"fecha_creacion":"2026-07-14","estado_label":"No gestionado"},
        {"fecha_creacion":"2026-07-14","estado_label":"Duplicado"}]
    r=antifunnel_serie(rr,"dia")
    assert r[0]=={"bucket":"2026-07-14","estados":{"Duplicado":2,"No gestionado":1}}

def test_contact_dist():
    assert contact_dist([{"state":"enviado"},{"state":"baja"},{"state":"enviado"}])=={"enviado":2,"baja":1}

def test_merge_neon_fills_missing():
    import agg
    mbm = {}
    agg.merge_neon_delivery(mbm, {"m1": {"status": "delivered", "error_name": "No Error (code 0)"}})
    assert mbm["m1"]["status"] == "delivered"

def test_merge_neon_terminal_overrides_pending():
    import agg
    mbm = {"m1": {"status": "pending", "error_name": "x", "seen": False}}
    agg.merge_neon_delivery(mbm, {"m1": {"status": "delivered", "error_name": "No Error (code 0)"}})
    assert mbm["m1"]["status"] == "delivered"

def test_merge_neon_does_not_regress_terminal_and_preserves_seen():
    import agg
    mbm = {"m1": {"status": "delivered", "error_name": "No Error (code 0)", "seen": True}}
    agg.merge_neon_delivery(mbm, {"m1": {"status": "pending", "error_name": "x"}})
    assert mbm["m1"]["status"] == "delivered" and mbm["m1"]["seen"] is True

def test_merge_neon_undeliverable_overrides_but_keeps_seen():
    import agg
    mbm = {"m1": {"status": "delivered", "error_name": "No Error (code 0)", "seen": True}}
    agg.merge_neon_delivery(mbm, {"m1": {"status": "undeliverable", "error_name": "EC_X (code 5)"}})
    assert mbm["m1"]["status"] == "undeliverable" and mbm["m1"]["seen"] is True
