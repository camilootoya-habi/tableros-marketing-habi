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


GUION_DIR = ("¡Perfecto! 🏡 Ya anoté que es una *casa*.\n\nAhora compárteme la *dirección* en texto, por favor:\n"
             "📍 *Estado*\n🛣️ *Calle*")
ACK = "¡Gracias! 🙌 Ya registré la *antigüedad*, *recámaras*, *baños*, *cajones* y el *valor pedido*."


# --- 1 pregunta_ignorada ---
def test_pregunta_ignorada_gabi_repite_el_mensaje_anterior():
    # validación manual: sólo es bug cuando Gabi REPITE en vez de responder. Si responde y además
    # sigue el guion en el mismo mensaje (lo habitual), no es bug.
    t = mk(('g', GUION_DIR, 0), ('u', '¿Cuánto me ofrecen por mi casa?', 1), ('g', GUION_DIR, 2))
    h = D.det_pregunta_ignorada(t, 'B')
    assert h and h[0]['subtipo'] == 'repitio_mensaje_anterior' and h[0]['idx'] == 1


def test_pregunta_ignorada_no_dispara_si_gabi_responde_y_sigue_el_guion():
    t = mk(('g', GUION_DIR, 0), ('u', '¿Cuánto tardan?', 1),
           ('g', '¡Claro! Toma 48 horas. Ahora compárteme la *dirección* en texto, por favor:', 2))
    assert D.det_pregunta_ignorada(t, 'B') == []


def test_pregunta_ignorada_ignora_autorespuesta_de_otro_negocio():
    # validación manual: 4 de 15 casos eran auto-respuestas de otro negocio (el teléfono no es del lead)
    t = mk(('g', GUION_DIR, 0),
           ('u', 'Gracias por comunicarte con Abarrotes los Chihuahuas. ¿Cómo podemos ayudarte?', 1),
           ('g', GUION_DIR, 2))
    assert D.det_pregunta_ignorada(t, 'B') == []


def test_pregunta_ignorada_ignora_que_y_como_sin_signo():
    # validación manual: 'la casa que compré' y 'como 80 m2' daban falsos positivos masivos
    t = mk(('g', GUION_DIR, 0), ('u', 'Es una casa que está en una privada, como 80 m2', 1), ('g', GUION_DIR, 2))
    assert D.det_pregunta_ignorada(t, 'B') == []


def test_pregunta_ignorada_bot_b_responde_con_nudge():
    t = mk(('g', 'hola', 0), ('u', 'y cuánto tardan?', 1), ('g', NUDGE, 121))
    assert D.det_pregunta_ignorada(t, 'B')[0]['subtipo'] == 'siguio_nudge'


def test_pregunta_ignorada_no_dispara_si_gabi_sale_del_guion():
    t = mk(('g', 'hola', 0), ('u', '¿Cuánto tardan?', 1), ('g', 'La evaluación toma 48 horas hábiles.', 2))
    assert D.det_pregunta_ignorada(t, 'B') == []


def test_pregunta_ignorada_ignora_respuesta_numerica_con_signo():
    # calibración: '3?' es una respuesta al bloque, no una pregunta
    t = mk(('g', BLOQUE, 0), ('u', '3?', 1), ('g', ACK, 2))
    assert D.det_pregunta_ignorada(t, 'B') == []


def test_pregunta_ignorada_acepta_pregunta_corta():
    # calibración: '¿Eres bot?' / 'Hay cobertura ?' son preguntas reales de 2-3 palabras
    t = mk(('g', GUION_DIR, 0), ('u', 'Eres bot?', 1), ('g', GUION_DIR, 2))
    assert D.det_pregunta_ignorada(t, 'B')


def test_pregunta_ignorada_no_dispara_si_gabi_sale_del_guion_2():
    t = mk(('g', GUION_DIR, 0), ('u', 'Eres bot?', 1), ('g', 'Soy un asistente virtual de TuHabi.', 2))
    assert D.det_pregunta_ignorada(t, 'B') == []


def test_pregunta_ignorada_ignora_el_signo_dentro_de_una_url():
    # calibración: las ubicaciones de WhatsApp llegan como https://maps.app.goo.gl/xxx?g_st=aw
    t = mk(('g', GUION_DIR, 0), ('u', 'https://maps.app.goo.gl/J1ZQb?g_st=aw', 1), ('g', GUION_DIR, 2))
    assert D.det_pregunta_ignorada(t, 'B') == []


# --- 2 ambigua_registrada ---
def test_ambigua_registrada_no_se_y_ack():
    t = mk(('g', BLOQUE, 0), ('u', 'no sé los metros, como 10 años, 3 recámaras', 1), ('g', ACK, 2))
    assert D.det_ambigua_registrada(t, 'B')[0]['subtipo'] == 'marcador_ambiguo'


def test_ambigua_registrada_sin_numeros_tras_bloque():
    t = mk(('g', BLOQUE, 0), ('u', 'es grande, tiene varias recámaras', 1), ('g', ACK, 2))
    assert D.det_ambigua_registrada(t, 'B')[0]['subtipo'] == 'sin_numeros'


def test_ambigua_no_dispara_si_gabi_repregunta():
    t = mk(('g', BLOQUE, 0), ('u', 'no sé los metros', 1), ('g', 'Solo me falta la *área construida*', 2))
    assert D.det_ambigua_registrada(t, 'B') == []


def test_ambigua_no_dispara_con_aprox_y_numero():
    # calibración: '150 mts 2 aprox.' es una respuesta usable, no una ambigüedad
    t = mk(('g', BLOQUE, 0), ('u', '25 años aprox, 190 m2, 4 recámaras, 3 baños, 2 cajones, 2 millones', 1), ('g', ACK, 2))
    assert D.det_ambigua_registrada(t, 'B') == []


def test_ambigua_no_dispara_con_no_tengo_cochera():
    # calibración: 'No tengo cochera' es un dato, no una ambigüedad
    t = mk(('g', BLOQUE, 0), ('u', '10 años, 120 m2, 3, 1 baño, no tengo cochera, 900 mil', 1), ('g', ACK, 2))
    assert D.det_ambigua_registrada(t, 'B') == []


# --- 3 repregunta_dato_ya_dado ---
def test_repregunta_area_ya_dada():
    t = mk(('g', BLOQUE, 0), ('u', '10 años\n120 m2\n3\n2\n1\n2,500,000', 1),
           ('g', 'Solo me falta la *área construida* en m²', 2))
    h = D.det_repregunta_dato_ya_dado(t, 'B')
    assert h and h[0]['subtipo'] == 'area'


def test_repregunta_precio_ya_dado():
    t = mk(('g', BLOQUE, 0), ('u', '10 años, 120 m2, 3, 2, 1, $2,500,000', 1),
           ('g', 'Solo me falta el *valor* que pides', 2))
    assert any(x['subtipo'] == 'precio' for x in D.det_repregunta_dato_ya_dado(t, 'B'))


def test_repregunta_no_dispara_si_el_dato_no_estaba():
    t = mk(('g', BLOQUE, 0), ('u', '10 años, 3 recámaras, 2 baños, 1 cajón, 2,500,000', 1),
           ('g', 'Solo me falta la *área construida*', 2))
    assert all(x['subtipo'] != 'area' for x in D.det_repregunta_dato_ya_dado(t, 'B'))


# --- 4 intencion_ignorada ---
def test_intencion_optout_seguida_de_guion():
    t = mk(('g', 'hola', 0), ('u', 'ya vendí la casa, gracias', 1), ('g', GUION_DIR, 2))
    assert D.det_intencion_ignorada(t, 'B')[0]['subtipo'] == 'opt_out'


def test_intencion_humano_seguida_de_nudge():
    t = mk(('g', 'hola', 0), ('u', 'prefiero que me llame un asesor', 1), ('g', NUDGE, 121))
    assert D.det_intencion_ignorada(t, 'B')[0]['subtipo'] == 'pide_humano'


def test_intencion_numero_equivocado():
    t = mk(('g', 'hola', 0), ('u', 'Tiene número equivocado.', 1), ('g', GUION_DIR, 2))
    assert D.det_intencion_ignorada(t, 'B')[0]['subtipo'] == 'numero_equivocado'


def test_intencion_no_dispara_si_gabi_la_atiende():
    t = mk(('g', 'hola', 0), ('u', 'ya vendí', 1), ('g', 'Entendido, cerramos tu solicitud. ¡Éxitos!', 2))
    assert D.det_intencion_ignorada(t, 'B') == []


def test_intencion_no_dispara_por_la_palabra_llama_en_se_llama():
    # calibración: 'un fraccionamiento que se llama igual' no es pedir que lo llamen
    t = mk(('g', GUION_DIR, 0), ('u', 'es un fraccionamiento que se llama Villas Santin', 1), ('g', GUION_DIR, 2))
    assert D.det_intencion_ignorada(t, 'B') == []


# --- 5 media_no_manejado ---
def test_media_url_maps_seguida_de_guion():
    t = mk(('g', GUION_DIR, 0), ('u', 'https://maps.app.goo.gl/2mWHhwEScLzMACHf8?g_st=ic', 1), ('g', GUION_DIR, 2))
    assert D.det_media_no_manejado(t, 'B')[0]['tipo'] == 'media_no_manejado'


def test_media_maps_apple():
    t = mk(('g', GUION_DIR, 0), ('u', 'https://maps.apple/p/b.BnFSBDraDDe.z', 1), ('g', NUDGE, 121))
    assert D.det_media_no_manejado(t, 'B')[0]['subtipo'] == 'ubicacion'


def test_media_no_dispara_si_gabi_acusa_la_ubicacion():
    t = mk(('g', GUION_DIR, 0), ('u', 'https://maps.app.goo.gl/abc', 1),
           ('g', 'Gracias, no puedo abrir enlaces. ¿Me escribes calle y número?', 2))
    assert D.det_media_no_manejado(t, 'B') == []


def test_latencia_alta_se_apaga_si_la_linea_de_tiempo_no_es_monotona():
    # calibración: 402 convs del bot A tienen saltos hacia atrás de meses (conversaciones de varios
    # periodos concatenadas). Ahí los deltas no significan nada, así que el detector no debe opinar.
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1), ('g', '¡Perfecto!', 15), ('u', 'ok', -50000))
    assert D.det_latencia_alta(t, 'B') == []


def test_repregunta_no_dispara_si_el_dato_no_trae_cantidad():
    # validación manual: 'cochera (entrada de casa)' no dice cuántos cajones -> re-preguntar es correcto
    t = mk(('g', BLOQUE, 0), ('u', '30 años, 90 m2, 2 recámaras, 1 baño, cochera, $1,700,000', 1),
           ('g', '¿cuántos *cajones de estacionamiento* tiene?', 2))
    assert all(x['subtipo'] != 'cajones' for x in D.det_repregunta_dato_ya_dado(t, 'B'))


def test_repregunta_cuenta_el_sin_estacionamiento():
    t = mk(('g', BLOQUE, 0), ('u', '44 años, 200 m2, sin estacionamiento, 4 millones', 1),
           ('g', 'Me faltan: *recámaras*, *baños* y *cajones de estacionamiento*', 2))
    assert any(x['subtipo'] == 'cajones' for x in D.det_repregunta_dato_ya_dado(t, 'B'))


def test_repregunta_no_toma_una_direccion_como_precio():
    # validación manual: 'Av México Coyoacán 372 torre H depto 1602, Cp 03230' pasaba como precio
    t = mk(('g', BLOQUE, 0), ('u', 'Av México Coyoacán 372 torre H depto 1602, col xoco, Cp 03230', 1),
           ('g', 'me faltan: *antigüedad*, *área construida* y *valor que pides* en MXN', 2))
    assert all(x['subtipo'] != 'precio' for x in D.det_repregunta_dato_ya_dado(t, 'B'))


def test_repregunta_no_confunde_terreno_con_area_construida():
    t = mk(('g', BLOQUE, 0), ('u', 'El terreno mide 6x15, con un total de 90 metros cuadrados', 1),
           ('g', 'Me faltan: *área construida* en m², *baños* y *precio*', 2))
    assert all(x['subtipo'] != 'area' for x in D.det_repregunta_dato_ya_dado(t, 'B'))


def test_repregunta_no_confunde_anos_pagando_con_antiguedad():
    t = mk(('g', BLOQUE, 0), ('u', 'La obtuve por Infonavit, tengo 7 años pagándola', 1),
           ('g', 'Me faltan: *antigüedad* en años y *área construida*', 2))
    assert all(x['subtipo'] != 'antiguedad' for x in D.det_repregunta_dato_ya_dado(t, 'B'))


def test_repregunta_no_confunde_una_deuda_con_el_precio():
    t = mk(('g', BLOQUE, 0), ('u', 'Debo 7 mil de predial y 103 mil al Infonavit', 1),
           ('g', 'Solo me falta el *valor que pides* en MXN', 2))
    assert all(x['subtipo'] != 'precio' for x in D.det_repregunta_dato_ya_dado(t, 'B'))


def test_repregunta_ignora_la_muletilla_de_las_escrituras():
    # validación manual: 'Si no recuerdas el área, suele venir en las escrituras' acompaña a OTRAS
    # peticiones y hacía contar una re-pregunta de área que nunca ocurrió
    t = mk(('g', BLOQUE, 0), ('u', '90 metros construidos, 1 cajón, $850,000', 1),
           ('g', 'Me faltan 2 datos: 📅 *Antigüedad* y 🛁 *Baños*. Si no recuerdas el área, suele venir en las escrituras', 2))
    assert all(x['subtipo'] != 'area' for x in D.det_repregunta_dato_ya_dado(t, 'B'))


def test_silencio_bot_ignora_las_cortesias():
    # validación manual: 'Ok' / 'Gracias' / '👍' tras el cierre no dejan nada pendiente
    t = mk(('g', 'Te contactaremos en breve ✨', 0), ('u', 'Ok gracias', 1))
    assert D.det_silencio_bot(t, 'B') == []


def test_nudge_anomalo_ignora_las_cortesias():
    t = mk(('g', GUION_DIR, 0), ('u', 'Ok', 1), ('g', NUDGE, 121))
    assert D.det_nudge_anomalo(t, 'B') == []


def test_nudge_anomalo_si_el_usuario_respondio_de_verdad():
    t = mk(('g', GUION_DIR, 0), ('u', 'Hola es casa y se encuentra en Nuevo Vallarta', 1), ('g', NUDGE, 121))
    assert D.det_nudge_anomalo(t, 'B')[0]['subtipo'] == 'nudge_tras_usuario'


def test_intencion_no_toma_una_correccion_como_numero_equivocado():
    # validación manual: 'Me equivoqué, la antigüedad es de 11 años' es una corrección, no un opt-out
    t = mk(('g', BLOQUE, 0), ('u', 'Me equivoqué, la antigüedad es de 11 años', 1), ('g', GUION_DIR, 2))
    assert D.det_intencion_ignorada(t, 'B') == []
