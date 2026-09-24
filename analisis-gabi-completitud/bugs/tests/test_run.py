from run import agregar


def test_agregar_cuenta_convs_no_hallazgos_y_cruza_ruteo():
    convs = [
        {'deal_id': 1, 'bot': 'B', 'etapa_muerte': '3_murio_en_direccion', 'ruteado': 0,
         'hallazgos': [{'tipo': 'pregunta_ignorada'}, {'tipo': 'pregunta_ignorada'}]},
        {'deal_id': 2, 'bot': 'B', 'etapa_muerte': '6_completo_o_paso', 'ruteado': 1, 'hallazgos': []},
        {'deal_id': 3, 'bot': 'A', 'etapa_muerte': '7_completo', 'ruteado': 1,
         'hallazgos': [{'tipo': 'silencio_bot'}]},
    ]
    r = agregar(convs)
    assert r['total']['convs'] == {'A': 1, 'B': 2}
    pi = r['por_tipo']['pregunta_ignorada']
    assert pi['hallazgos'] == 2 and pi['convs'] == {'B': 1}
    assert pi['pct_convs']['B'] == 50.0
    assert pi['por_etapa']['B']['3_murio_en_direccion'] == 1
    assert pi['ruteo']['con_bug'] == 0.0 and pi['ruteo']['sin_bug'] == 100.0
