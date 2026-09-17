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


# ── Recordación espontánea: se transcribe, no se interpreta ───────────────────

def test_la_espontanea_pasa_tal_cual_sin_codificar_marcas():
    # Pulso agrupa por ortografía y NO interpreta (una variante mal escrita es su propio
    # grupo). El tablero mantiene ese criterio: transcribe el ranking, no lo codifica.
    assert fila()["espontanea"] == [{"texto": "Inmuebles24", "n": 30}, {"texto": "TuHabi", "n": 12}]


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
