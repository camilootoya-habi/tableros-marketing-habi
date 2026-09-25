import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_pulso as P

# Recorte real de lo que devuelve /api/resultados de Pulso: solo agregados.
PAYLOAD = {
    "wave_id": "2026Q3",
    "updated_at": "2026-09-15T21:00:00Z",
    "totals": {"opened": 120, "completed": 72, "completion_pct": 60,
               "median_duration_sec": 180,
               "by_channel": [{"channel": "wa", "count": 62}, {"channel": "voz", "count": 10}]},
    "q1": {"items": [{"text": "Inmuebles24", "count": 30}, {"text": "TuHabi", "count": 12}],
           "distinct": 2, "total": 72},
    "q2": {"texts": [], "none_count": 0, "total": 72},
    "q3": {"bars": [{"id": "inmuebles24", "label": "Inmuebles24", "count": 58, "pct": 81},
                    {"id": "tuhabi", "label": "TuHabi", "count": 40, "pct": 56},
                    {"id": "fake", "label": "Vendecasa Express", "count": 6, "pct": 8},
                    {"id": "ninguna", "label": "Ninguna", "count": 4, "pct": 6}],
           "none_count": 0, "total": 72},
    "q4": {"bars": [{"id": "tuhabi", "label": "TuHabi", "count": 22, "pct": 31}], "total": 72},
    "q5": {"bars": [{"id": "tuhabi", "label": "TuHabi", "count": 8, "pct": 11}], "total": 72},
    "q7": [{"brand": "tuhabi", "label": "TuHabi", "n": 38, "ns": 2,
            "items": [{"id": "necesita", "text": "Resuelve lo que necesito", "avg": 4.1},
                      {"id": "confio", "text": "Es una marca en la que confío", "avg": 3.7}]}],
    "q8": {"texts": [], "total": 72},
}


def fila(payload=PAYLOAD):
    return P.series([payload])[0]


# ── El embudo de la marca focal ───────────────────────────────────────────────

def test_la_fila_lleva_el_embudo_de_la_marca_focal():
    f = fila()
    assert f["wave"] == "2026Q3"
    assert f["respuestas"] == 72
    assert f["asistida_pct"] == 56        # Q3: la conocen
    assert f["consideracion_pct"] == 31   # Q4: la considerarían
    assert f["primera_opcion_pct"] == 11  # Q5: su primera opción


def test_una_marca_que_no_aparece_en_la_pregunta_queda_en_cero_no_en_none():
    p = dict(PAYLOAD, q5={"bars": [], "total": 72})
    assert fila(p)["primera_opcion_pct"] == 0


# ── La marca de control no se mezcla con la competencia ───────────────────────

def test_la_marca_falsa_no_aparece_como_competidora():
    marcas = [c["marca"] for c in fila()["competencia"]]
    assert "Vendecasa Express" not in marcas
    assert "Inmuebles24" in marcas


def test_la_marca_falsa_se_publica_aparte_como_piso_de_ruido():
    assert fila()["ruido_pct"] == 8


def test_ninguna_no_es_una_marca_y_no_entra_en_la_competencia():
    """'Ninguna' es la opción de no conocer ninguna, no un competidor: listarla entre
    Inmuebles24 y Lamudi la hace leer como una marca más."""
    assert "Ninguna" not in [c["marca"] for c in fila()["competencia"]]


def test_cuantos_no_conocen_ninguna_se_publica_como_dato_propio():
    assert fila()["ninguna_pct"] == 6


def test_la_marca_focal_tampoco_se_cuenta_como_competidora():
    assert "TuHabi" not in [c["marca"] for c in fila()["competencia"]]


# ── Recordación espontánea: misma agrupación que Q1 ───────────────────────────

def test_la_espontanea_usa_la_misma_agrupacion_que_q1():
    # Si el ranking de la agrupación y el de Q1 usaran criterios distintos, la misma marca
    # tendría dos cifras en el mismo tablero.
    p = dict(PAYLOAD, q1={"items": [{"text": "Inmuebles 24", "count": 5},
                                    {"text": "inmuebles24", "count": 2}], "distinct": 2, "total": 7})
    assert fila(p)["espontanea"] == [{"texto": "Inmuebles24", "n": 7}]
    assert fila(p)["preguntas"]["q1"]["grupos"] == [{"grupo": "Inmuebles24", "n": 7}]


# ── Atributos ─────────────────────────────────────────────────────────────────

def test_los_atributos_son_los_de_la_marca_focal_con_su_base():
    f = fila()
    assert f["atributos_n"] == 38
    assert {a["id"]: a["avg"] for a in f["atributos"]} == {"necesita": 4.1, "confio": 3.7}


# ── Robustez ──────────────────────────────────────────────────────────────────

def test_una_ola_sin_respuestas_no_revienta_y_da_ceros():
    vacio = {"wave_id": "2026Q4", "totals": {"opened": 0, "completed": 0, "completion_pct": 0,
                                             "median_duration_sec": None, "by_channel": []},
             "q1": {"items": [], "distinct": 0, "total": 0},
             "q3": {"bars": [], "none_count": 0, "total": 0},
             "q4": {"bars": [], "total": 0}, "q5": {"bars": [], "total": 0}, "q7": [],
             "q8": {"texts": [], "total": 0}}
    f = fila(vacio)
    assert f["respuestas"] == 0
    assert f["asistida_pct"] == 0
    assert f["atributos"] == []


def test_la_serie_va_ordenada_por_ola():
    b = dict(PAYLOAD, wave_id="2026Q4")
    assert [r["wave"] for r in P.series([b, PAYLOAD])] == ["2026Q3", "2026Q4"]


def test_la_serie_nunca_arrastra_datos_de_personas():
    import json
    crudo = json.dumps(P.series([PAYLOAD]))
    # Como claves JSON: "uid" a secas daría un falso positivo con "ruido_pct".
    for prohibido in ('"utm_name"', '"utm_phone"', '"telefono"', '"uid"', '"ip_hash"'):
        assert prohibido not in crudo


# ---------------------------------------------------------------------------
# Audiencia: la encuesta se manda a dueños y a agentes inmobiliarios, y la
# salud de marca se mide sobre los dueños, que son el cliente de TuHabi.
# Sin pedir audiencia la API devuelve los dos públicos mezclados.
# ---------------------------------------------------------------------------


class _Respuesta:
    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    def read(self):
        return self._cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _espiar_urlopen(cuerpo=b'{"wave_id":"X","audience":"owner","totals":{"completed":1}}'):
    pedidos = []
    original = P.urllib.request.urlopen

    def falso(destino, timeout=None):
        pedidos.append(destino)
        return _Respuesta(cuerpo)

    P.urllib.request.urlopen = falso
    return pedidos, original


def test_fetch_pide_solo_la_audiencia_de_duenos_por_defecto():
    pedidos, original = _espiar_urlopen()
    try:
        P.fetch()
    finally:
        P.urllib.request.urlopen = original
    assert "audience=owner" in pedidos[0]


def test_fetch_puede_pedir_la_audiencia_de_agentes():
    pedidos, original = _espiar_urlopen()
    try:
        P.fetch(audiencia="broker")
    finally:
        P.urllib.request.urlopen = original
    assert "audience=broker" in pedidos[0]


def test_fetch_combina_ola_y_audiencia_en_la_misma_url():
    pedidos, original = _espiar_urlopen()
    try:
        P.fetch(wave="2026Q3")
    finally:
        P.urllib.request.urlopen = original
    assert "wave=2026Q3" in pedidos[0] and "audience=owner" in pedidos[0]


def test_la_fila_deja_dicho_de_que_publico_es():
    f = P.fila({**PAYLOAD, "audience": "owner"})
    assert f["audiencia"] == "owner"


# ── Pregunta por pregunta ─────────────────────────────────────────────────────

def test_la_fila_trae_cada_pregunta_en_el_orden_de_la_encuesta():
    q = fila()["preguntas"]
    assert list(q) == ["q1", "q2", "q3", "q4", "q5", "q7", "q8"]   # no hay Q6
    assert q["q1"]["grupos"][0] == {"grupo": "Inmuebles24", "n": 30}
    assert q["q3"]["total"] == 72


def test_q3_conserva_la_marca_ficticia_y_ninguna_para_mostrarlas_rotuladas():
    ids = [b["id"] for b in fila()["preguntas"]["q3"]["barras"]]
    assert "fake" in ids and "ninguna" in ids


def test_q7_trae_todas_las_marcas_evaluadas_no_solo_la_focal():
    otra = {"brand": "lamudi", "label": "Lamudi", "n": 10, "ns": 1,
            "items": [{"id": "confio", "text": "Es una marca en la que confío", "avg": 3.0}]}
    p = dict(PAYLOAD, q7=PAYLOAD["q7"] + [otra])
    assert [m["marca"] for m in fila(p)["preguntas"]["q7"]] == ["tuhabi", "lamudi"]


def test_las_abiertas_se_publican_agrupadas_no_como_texto_crudo():
    p = dict(PAYLOAD, q8={"texts": ["Compran rápido", {"raro": 1}], "total": 5})
    q8 = fila(p)["preguntas"]["q8"]
    assert q8 == {"grupos": [{"grupo": "Compran tu casa", "n": 1, "ejemplo": "Compran rápido"}],
                  "muestra": 1, "total": 5}


# ── Agrupación de abiertas ────────────────────────────────────────────────────

def test_variantes_de_una_marca_se_juntan():
    g = P.agrupar_marcas([("Inmuebles 24", 24), ("Inmuebkes 24", 1), ("I24", 1),
                          ("Inmuebles veinticuatro", 2)])
    assert g == [{"grupo": "Inmuebles24", "n": 28}]


def test_una_respuesta_con_varias_marcas_suma_a_cada_una():
    g = {x["grupo"]: x["n"] for x in P.agrupar_marcas([("Century 21 y ibmuwbles 24", 1),
                                                       ("Inmuebles 24 easy broker facebook", 1)])}
    assert g == {"Inmuebles24": 2, "Century 21": 1, "EasyBroker": 1, "Facebook / Marketplace": 1}


def test_lo_que_no_se_reconoce_queda_como_su_propio_grupo():
    g = P.agrupar_marcas([("Maglen realty group", 1), ("Lamudi", 2)])
    assert g == [{"grupo": "Lamudi", "n": 2}, {"grupo": "Maglen realty group", "n": 1}]


def test_una_variante_corta_solo_cuenta_como_respuesta_entera():
    # "ig" dentro de "Vigilancia" no es Instagram.
    assert P.agrupar_marcas([("Vigilancia", 1)]) == [{"grupo": "Vigilancia", "n": 1}]
    assert P.agrupar_marcas([("IG", 1)]) == [{"grupo": "Instagram", "n": 1}]


def test_ninguna_no_se_suma_si_la_respuesta_nombra_marcas():
    assert P.agrupar_marcas([("No recuerdo propiedades.com", 1)]) == [
        {"grupo": "Propiedades.com", "n": 1}]


def test_temas_q8_la_queja_gana_sobre_la_descripcion():
    g = P.agrupar_temas(["Compran barato para vender caro", "Compra rápida de propiedades"])
    assert {x["grupo"]: x["n"] for x in g} == {"Opinión negativa": 1, "Compran tu casa": 1}


def test_temas_q8_lo_que_no_coincide_va_a_otras():
    assert P.agrupar_temas(["Conectividad"]) == [
        {"grupo": "Otras", "n": 1, "ejemplo": "Conectividad"}]


def test_series_separa_duenos_y_brokers_de_la_misma_ola():
    s = P.series([dict(PAYLOAD, audience="owner"), dict(PAYLOAD, audience="broker")])
    assert [f["audiencia"] for f in s] == ["broker", "owner"]
