from datetime import datetime, timedelta
from parse import Turn
import detectores as D

T0 = datetime(2026, 7, 1, 10, 0, 0)


def mk(*pares):
    """mk(('g', 'texto', minutos), ('u', 'texto', minutos), ...) -> list[Turn]"""
    out = []
    for i, (rol, texto, mins) in enumerate(pares):
        out.append(Turn(i, 'gabi' if rol == 'g' else 'usuario', texto, T0 + timedelta(minutes=mins)))
    return out


NUDGE = "*Sigo pendiente de tu respuesta*\n\n📌 Cuando tengas oportunidad"
BLOQUE = ("Ahora ayúdame con estos datos:\n📅 *Antigüedad* en años\n📏 *Área construida* en m²\n"
          "🛏️ *Recámaras*\n🛁 *Baños*\n🚗 *Cajones*\n💰 *Valor que pides*")


# --- 6 silencio_bot ---
def test_silencio_bot_ultimo_turno_usuario():
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1))
    h = D.det_silencio_bot(t, 'B')
    assert [x['tipo'] for x in h] == ['silencio_bot'] and h[0]['subtipo'] == 'sin_respuesta_final'


def test_silencio_bot_solo_nudge():
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1), ('g', NUDGE, 121))
    assert D.det_silencio_bot(t, 'B')[0]['subtipo'] == 'solo_nudge'


def test_silencio_bot_no_dispara_si_gabi_contesta():
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1), ('g', '¡Perfecto! Ya anoté', 2))
    assert D.det_silencio_bot(t, 'B') == []


# --- 7 nudge_anomalo ---
def test_nudge_tras_respuesta_del_usuario():
    t = mk(('g', BLOQUE, 0), ('u', '10 años, 120 m2, 3, 2, 1, 2 millones', 3), ('g', NUDGE, 120))
    h = D.det_nudge_anomalo(t, 'B')
    assert h and h[0]['subtipo'] == 'nudge_tras_usuario'


def test_nudge_doble():
    t = mk(('g', BLOQUE, 0), ('g', NUDGE, 120), ('g', NUDGE, 240))
    assert any(x['subtipo'] == 'nudge_doble' for x in D.det_nudge_anomalo(t, 'B'))


def test_nudge_normal_no_dispara():
    t = mk(('g', BLOQUE, 0), ('g', NUDGE, 120))
    assert D.det_nudge_anomalo(t, 'B') == []


# --- 8 loop_repeticion ---
def test_loop_mismo_mensaje_dos_veces():
    t = mk(('g', 'Compárteme la *dirección*', 0), ('u', 'Calle 5', 1), ('g', 'Compárteme la *dirección*', 2))
    assert D.det_loop_repeticion(t, 'B')[0]['subtipo'] == 'mensaje_repetido'


def test_loop_ignora_el_nudge():
    t = mk(('g', BLOQUE, 0), ('g', NUDGE, 120), ('g', NUDGE, 1560))
    assert all(x['subtipo'] != 'mensaje_repetido' for x in D.det_loop_repeticion(t, 'B'))


def test_loop_mismo_campo_tres_veces():
    f = "Solo me falta la *área construida* en m²"
    t = mk(('g', f, 0), ('u', 'no sé', 1), ('g', f + ' 😊', 2), ('u', 'mmm', 3), ('g', f + '!!', 4))
    assert any(x['subtipo'] == 'campo_repreguntado_3x' for x in D.det_loop_repeticion(t, 'B'))


# --- 9 duplicado_gabi ---
def test_duplicado_gabi_mismo_texto_en_1_min():
    t = mk(('g', 'hola', 0), ('g', 'hola', 1))
    assert D.det_duplicado_gabi(t, 'B')[0]['tipo'] == 'duplicado_gabi'


def test_duplicado_gabi_no_si_pasan_5_min():
    t = mk(('g', 'hola', 0), ('g', 'hola', 5))
    assert D.det_duplicado_gabi(t, 'B') == []


# --- 10 plantilla_rota ---
def test_plantilla_rota_none_y_llaves():
    assert D.det_plantilla_rota(mk(('g', '¡Hola, None! bienvenido', 0)), 'B')
    assert D.det_plantilla_rota(mk(('g', 'Hola {nombre}', 0)), 'B')
    assert D.det_plantilla_rota(mk(('g', '¡Hola, !', 0)), 'B')


def test_plantilla_rota_no_falsos_positivos_en_usuario():
    assert D.det_plantilla_rota(mk(('u', 'None', 0)), 'B') == []


# --- 11 hora_no_monotona ---
def test_hora_no_monotona():
    t = mk(('g', 'a', 10), ('u', 'b', 5))
    assert D.det_hora_no_monotona(t, 'B')[0]['tipo'] == 'hora_no_monotona'


# --- 12 latencia_alta ---
def test_latencia_alta_gabi_tarda_mas_de_10_min():
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1), ('g', '¡Perfecto!', 15))
    assert D.det_latencia_alta(t, 'B')[0]['tipo'] == 'latencia_alta'


def test_latencia_alta_ignora_nudge():
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1), ('g', NUDGE, 121))
    assert D.det_latencia_alta(t, 'B') == []
