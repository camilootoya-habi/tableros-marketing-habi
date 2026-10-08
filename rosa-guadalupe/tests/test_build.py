import json

import rosa_build as B

CFG = {"inicio_organico": "2026-10-02", "inicio_pagado": "2026-10-02", "patron": "rosa|guadalupe|🌹",
       "incluir": [], "excluir": [], "prefijo_ads": "Rosa", "cuenta_ads": "act_1"}


def test_clasificar_regla_incluir_excluir():
    posts = [{"id": "a", "fecha": "2026-10-03", "texto_completo": "Una señal 🌹"},
             {"id": "b", "fecha": "2026-10-03", "texto_completo": "La ROSA de Guadalupe"},
             {"id": "c", "fecha": "2026-10-03", "texto_completo": "Vende tu casa"},
             {"id": "d", "fecha": "2026-09-30", "texto_completo": "rosa antes de la acción"},
             {"id": "e", "fecha": "2026-10-04", "texto_completo": "rosa pero no es"}]
    cfg = dict(CFG, incluir=["c"], excluir=["e"])
    assert [p["id"] for p in B.clasificar(posts, cfg)] == ["a", "b", "c"]


def test_pieza_quita_plataforma():
    assert B.pieza("Rosa_6_Instagram_Desempleado") == "Rosa_6_Desempleado"
    assert B.pieza("Rosa_6_Facebook_Desempleado") == "Rosa_6_Desempleado"
    assert B.pieza("Rosa_6_Desempleado") == "Rosa_6_Desempleado"
    assert B.pieza("Rosa_con_pleca") == "Rosa_con_pleca"


def test_objetivo():
    assert B.objetivo("OUTCOME_AWARENESS") == "alcance"
    assert B.objetivo("OUTCOME_SALES") == "leads"
    assert B.objetivo("OUTCOME_ENGAGEMENT") == "interaccion"
    assert B.objetivo("RARO") == "otro"


def test_metricas_fila():
    f = {"spend": "1.99", "impressions": "4582", "clicks": "5", "inline_link_clicks": "2", "estimated_ad_recallers": "1",
         "actions": [{"action_type": "link_click", "value": "2"}, {"action_type": "landing_page_view", "value": "1"},
                     {"action_type": "post_engagement", "value": "390"}, {"action_type": "video_view", "value": "387"},
                     {"action_type": "post", "value": "3"}, {"action_type": "lead", "value": "4"},
                     {"action_type": "offsite_conversion.fb_pixel_lead", "value": "4"}],
         "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "36"}]}
    m = B.metricas_fila(f)
    assert m == {"inversion": 1.99, "impresiones": 4582, "clics": 5, "clics_link": 2, "landing": 1, "interacciones": 390,
                 "video_3s": 387, "compartidos": 3, "leads": 4, "thruplay": 36, "recordacion": 1}


def test_metricas_fila_lead_sin_pixel_explicito():
    m = B.metricas_fila({"spend": "1", "actions": [{"action_type": "lead", "value": "2"}]})
    assert m["leads"] == 2


def test_comparativo_resta_rosa_de_la_campana_en_los_mismos_dias():
    rosa = [{"d": "2026-10-06", "campana_id": "c1", "campana": "Conv", "obj": "leads", "inversion": 10, "impresiones": 1000, "leads": 5},
            {"d": "2026-10-07", "campana_id": "c1", "campana": "Conv", "obj": "leads", "inversion": 20, "impresiones": 2000, "leads": 5}]
    camp = [{"d": "2026-10-05", "campana_id": "c1", "inversion": 999, "impresiones": 1},   # antes de Rosa: fuera
            {"d": "2026-10-06", "campana_id": "c1", "inversion": 50, "impresiones": 5000, "leads": 20},
            {"d": "2026-10-07", "campana_id": "c1", "inversion": 50, "impresiones": 5000, "leads": 20}]
    (c,) = B.comparativo(rosa, camp)
    assert c["desde"] == "2026-10-06" and c["hasta"] == "2026-10-07"
    assert c["rosa"] == {"inversion": 30, "impresiones": 3000, "leads": 10}
    assert c["otros"] == {"inversion": 70, "impresiones": 7000, "leads": 30}


def test_promedio_previo_excluye_pautados_y_fuera_de_ventana():
    social = {"posts": {"MX": {
        "1": {"fecha": "2026-09-10", "vistas": 100, "alcance": 80, "interacciones": 10},
        "2": {"fecha": "2026-09-20", "vistas": 300, "alcance": 200, "interacciones": 30},
        "3": {"fecha": "2026-09-21", "vistas": 9000, "pauta": True},
        "4": {"fecha": "2026-10-03", "vistas": 9000},
        "5": {"fecha": "2026-05-01", "vistas": 9000}}},
        "fb_posts": {"MX": {"f": {"fecha": "2026-09-15", "vistas": 50, "reacciones": 3, "comentarios": 1, "compartidos": 1}}}}
    p = B.promedio_previo(social, "2026-10-02")
    assert p["ig"]["n"] == 2 and p["ig"]["vistas"] == 200 and p["ig"]["interacciones"] == 20
    assert p["fb"]["n"] == 1 and p["fb"]["interacciones"] == 5


def test_cuenta_compara_14_dias_antes_contra_despues():
    datos = {f"2026-09-{d:02d}": {"ig_perfil_d": 10} for d in range(18, 31)}
    datos["2026-10-01"] = {"ig_perfil_d": 10}
    datos["2026-10-02"] = {"ig_perfil_d": 30}
    datos["2026-10-03"] = {"ig_perfil_d": 50}
    c = B.cuenta({"datos": {"MX": datos}}, "2026-10-02", "2026-10-07")
    assert c["periodos"]["ig_perfil_d"]["antes"] == {"prom": 10.0, "dias": 14, "total": 140}
    assert c["periodos"]["ig_perfil_d"]["despues"]["prom"] == 40.0
    assert c["periodos"]["fb_altas"]["antes"] is None


def test_una_fuente_caida_no_tumba_las_otras():
    """Sin token: pagado y orgánico fallan (error, sin caché); cuenta sale ok del social_cache."""
    json.dump({"datos": {"MX": {"2026-10-03": {"ig_perfil_d": 5}}}}, open(B.SOCIAL_CACHE, "w"))
    d = B.build(hoy="2026-10-07", ahora="2026-10-07T12:00:00Z")
    assert d["pagado"]["status"] == "error" and "token" in d["pagado"]["reason"]
    assert d["organico"]["status"] == "error"
    assert d["cuenta"]["status"] == "ok"


def test_fuente_caida_sale_stale_desde_el_cache():
    json.dump({"pagado": {"status": "ok", "filas": [{"d": "2026-10-06"}], "anuncios": {}}}, open(B.CACHE, "w"))
    d = B.build(hoy="2026-10-07", ahora="2026-10-07T12:00:00Z")
    assert d["pagado"]["status"] == "stale" and d["pagado"]["filas"] == [{"d": "2026-10-06"}]
    assert d["cuenta"]["status"] == "error"   # tampoco hay social_cache


def test_metricas_fila_separa_vista_y_valor_de_compras():
    f = {"spend": "10", "actions": [{"action_type": "offsite_conversion.fb_pixel_lead", "value": "408", "1d_view": "21", "7d_click": "387"},
                                    {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "8", "1d_view": "3"}],
         "action_values": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "1400.5"}]}
    m = B.metricas_fila(f)
    assert (m["leads"], m["leads_vista"], m["compras"], m["compras_vista"], m["valor_compras"]) == (408, 21, 8, 3, 1400.5)


def test_optimizacion_de_en_palabras():
    o = B.optimizacion_de({"name": "x", "optimization_goal": "VALUE", "promoted_object": {"custom_event_type": "PURCHASE"},
                           "attribution_spec": [{"event_type": "CLICK_THROUGH", "window_days": 7}, {"event_type": "VIEW_THROUGH", "window_days": 1}]})
    assert o["meta"] == "Valor de la conversión" and o["evento"] == "PURCHASE"
    assert o["atribucion"] == "7 días clic + 1 día vista"


def test_miniaturas_borra_las_que_salen_con_su_grande(tmp_path):
    import os
    os.makedirs(B.MINIATURAS)
    for f in ("viejo.jpg", "viejo_g.jpg", "queda.jpg"):
        open(os.path.join(B.MINIATURAS, f), "wb").write(b"x")
    con = B.miniaturas(["queda"], {})
    assert sorted(os.listdir(B.MINIATURAS)) == ["queda.jpg"] and con == {"queda"}


def test_ig_dia_separa_anuncios_y_pide_el_dia_correcto(monkeypatch):
    pedidos = []

    def falso(path, **p):
        pedidos.append((p["since"], p["until"]))
        res = lambda tipos: {"breakdowns": [{"results": [{"dimension_values": [k], "value": v} for k, v in tipos.items()]}]}
        if p["metric"] == "follows_and_unfollows":
            return {"data": [{"name": "follows_and_unfollows", "total_value": res({"FOLLOWER": 33, "NON_FOLLOWER": 9})}]}
        return {"data": [{"name": "views", "total_value": res({"AD": 1000, "REEL": 30, "STORY": 5, "PROFILE_PIC": 1})},
                         {"name": "likes", "total_value": res({"AD": 90, "REEL": 48, "STORY": 5})},
                         {"name": "reach", "total_value": res({"AD": 800, "REEL": 20})},
                         {"name": "total_interactions", "total_value": res({"AD": 9, "REEL": 4})}]}
    monkeypatch.setattr(B, "_get", falso)
    v = B.ig_dia("2026-10-05", "tok")
    assert v["vistas_org"] == 36 and v["vistas_ads"] == 1000 and v["vistas_reel"] == 30 and v["vistas_story"] == 5
    assert v["alcance_org"] == 20 and v["inter_org"] == 4
    assert (v["likes_org"], v["likes_ads"], v["likes_reel"]) == (53, 90, 48)
    assert (v["altas"], v["bajas"]) == (33, 9)
    # El día 5 de Meta se pide con la ventana [6-oct, 7-oct) en UTC (las dos llamadas).
    ventana = (B.SOCIAL._ts(B.datetime.date(2026, 10, 6)), B.SOCIAL._ts(B.datetime.date(2026, 10, 7)))
    assert pedidos == [ventana, ventana]


def test_dias_ig_a_pedir_solo_faltantes_viejos_y_recientes():
    guardados = {f"2026-10-0{d}": {"altas": 1} for d in range(1, 7)}
    guardados["2026-10-02"] = {"vistas_org": 5}   # de la versión anterior: sin altas → se repide
    assert B.dias_ig_a_pedir(guardados, "2026-09-30", "2026-10-07") == \
        ["2026-09-30", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07"]


def test_ultimo_cerrado_respeta_el_corte_de_las_7_utc():
    utc = B.datetime.timezone.utc
    assert B.ultimo_cerrado(B.datetime.datetime(2026, 10, 8, 2, 0, tzinfo=utc)) == "2026-10-06"
    assert B.ultimo_cerrado(B.datetime.datetime(2026, 10, 8, 8, 0, tzinfo=utc)) == "2026-10-07"


def test_tono_de_reacciones():
    assert B.tono({"like": 10, "love": 2, "haha": 1, "sorry": 3, "anger": 1}) == (13, 4)


def test_fb_serie_con_desglose_de_anuncios():
    vals = [{"end_time": "2026-10-06T07:00:00+0000", "is_from_ads": "0", "value": 3},
            {"end_time": "2026-10-06T07:00:00+0000", "is_from_ads": "1", "value": 900}]
    assert B.fb_serie(vals, "is_from_ads") == {"2026-10-05": {"0": 3, "1": 900}}


def test_organico_cuenta_caida_sale_error_sin_tumbar_el_resto():
    d = B.build(hoy="2026-10-07", ahora="2026-10-07T12:00:00Z")
    assert d["organico_cuenta"]["status"] == "error" and "token" in d["organico_cuenta"]["reason"]
    assert set(d) >= {"pagado", "organico", "cuenta"}


def test_fb_serie_altas_pagadas_y_reacciones_por_tipo():
    vals = [{"end_time": "2026-10-06T07:00:00+0000", "value": {"total": 29, "paid": 16, "unpaid": 13}}]
    assert B.fb_serie(vals) == {"2026-10-05": {"total": 29, "paid": 16, "unpaid": 13}}


def test_posiciones_suman_lo_mismo_que_el_total():
    filas = [{"inversion": 1.5, "impresiones": 10, "pos": "feed"}, {"inversion": 2.25, "impresiones": 30, "pos": "instagram_reels"}]
    assert B.sumar(filas) == {"inversion": 3.75, "impresiones": 40}


def test_posts_con_comentarios_sin_repetir_post():
    posts = [{"id": "ig1", "red": "ig", "link": "L1"}]
    anuncios = {"a1": {"pieza": "Rosa_2_Queretaro", "obj": "leads", "post_fb": "P_1", "post_ig": "ig1"},
                "a2": {"pieza": "Rosa_2_Queretaro", "obj": "alcance", "post_fb": "P_1"}}
    v = B.posts_con_comentarios(posts, anuncios)
    assert set(v) == {("ig", "ig1"), ("fb", "P_1")}
    assert v[("ig", "ig1")]["canal"] == "organico"          # un post orgánico usado en un anuncio sigue siendo orgánico
    assert v[("fb", "P_1")]["canal"] == "pago" and v[("fb", "P_1")]["objs"] == {"leads", "alcance"}


def test_comentarios_fb_marca_respuesta_y_quita_los_de_la_pagina(monkeypatch):
    datos = [{"id": "1", "message": "¿Cómo vendo?", "created_time": "2026-10-07T10:00:00+0000", "from": {"id": "u", "name": "Ana"},
              "comments": {"data": [{"from": {"id": B.PAGE_ID}}]}},
             {"id": "2", "message": "Pésimos", "created_time": "2026-10-07T11:00:00+0000"},
             {"id": "3", "message": "Gracias, Ana", "from": {"id": B.PAGE_ID}}]
    monkeypatch.setattr(B, "_todas", lambda path, **p: datos)
    cs = B.comentarios_fb("P_1", "tok")
    assert [(c["id"], c["respondido"], c["autor"]) for c in cs] == [("1", True, "Ana"), ("2", False, None)]


def test_comentarios_ig_respondido_por_la_cuenta(monkeypatch):
    datos = [{"id": "1", "text": "jajaja", "username": "x", "replies": {"data": [{"username": "tuhabimx"}]}},
             {"id": "2", "text": "Gracias", "username": "tuhabimx"}]
    monkeypatch.setattr(B, "_todas", lambda path, **p: datos)
    cs = B.comentarios_ig("m1", "tok", "tuhabimx")
    assert [(c["id"], c["respondido"]) for c in cs] == [("1", True)]
