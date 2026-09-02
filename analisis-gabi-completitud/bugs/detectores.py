"""Detectores de fallas del agente. Cada det_<tipo>(turns, bot) -> list[hallazgo].
hallazgo = {"tipo", "subtipo", "idx", "evidencia"}. Regex sobre texto de LLM: validar SIEMPRE con muestra (Task 6)."""
import re
import unicodedata
from parse import Turn, is_nudge

# ---------- constantes compartidas ----------
FALTA = {   # campo -> regex del "Solo me falta ... <campo>" del bot B
    'area':       r'[áa]rea construida',
    'precio':     r'valor|precio',
    'antiguedad': r'antig[üu]edad',
    'recamaras':  r'rec[áa]maras',
    'banos':      r'ba[ñn]os',
    'cajones':    r'cajones|estacionamiento',
}
RE_FALTA = {k: re.compile(r'falta[\s\S]{0,200}?(' + v + ')', re.I) for k, v in FALTA.items()}
# Muletilla que menciona el área SIN pedirla ("si no la recuerdas, suele venir en las escrituras"):
# se quita antes de buscar la re-pregunta, si no infla el conteo de área. Vista en la validación manual.
RE_MULETILLA = re.compile(r'si no (la |lo |las |los )?(recuerdas|sabes)[^.\n]{0,120}|suele venir en las \*?escrituras\*?[^.\n]{0,40}', re.I)
RE_PLANTILLA_ROTA = re.compile(r'\bNone\b|\bnull\b|\bnan\b|\{\{|\{[a-z_]+\}|\bundefined\b|\[object|¡Hola, !|Hola, ,', re.I)
LATENCIA_MAX_S = 600
DUPLICADO_MAX_S = 120


def _h(tipo, turn, subtipo=None):
    return {'tipo': tipo, 'subtipo': subtipo, 'idx': turn.idx, 'evidencia': turn.texto[:200]}


def _norm(texto: str) -> str:
    """Minúsculas, sin acentos, sin emojis/puntuación, sin nombre del saludo. Para comparar mensajes de Gabi."""
    t = re.sub(r'¡?Hola,?\s+[^!\n*]{2,60}!', 'hola', texto)
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9 ]+', ' ', t.lower()).strip()


def _dt(a: Turn, b: Turn):
    if a.hora is None or b.hora is None:
        return None
    return (b.hora - a.hora).total_seconds()


# ---------- 6 silencio_bot ----------
def det_silencio_bot(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario' or RE_MULETILLA_USUARIO.match(t.texto) or RE_AUTORESPUESTA.search(t.texto):
            continue   # una cortesía sin contenido no deja nada pendiente de responder
        despues = turns[i + 1:]
        if not despues:
            out.append(_h('silencio_bot', t, 'sin_respuesta_final'))
        elif all(x.rol == 'gabi' and is_nudge(x.texto) for x in despues):
            out.append(_h('silencio_bot', t, 'solo_nudge'))
    return out


# ---------- 7 nudge_anomalo ----------
def det_nudge_anomalo(turns, bot):
    if not es_monotona(turns):
        return []   # orden de turnos no confiable (ver es_monotona)
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'gabi' or not is_nudge(t.texto) or i == 0:
            continue
        prev = turns[i - 1]
        if prev.rol == 'usuario' and not RE_MULETILLA_USUARIO.match(prev.texto):
            out.append(_h('nudge_anomalo', t, 'nudge_tras_usuario'))
        elif prev.rol == 'gabi' and is_nudge(prev.texto):
            out.append(_h('nudge_anomalo', t, 'nudge_doble'))
    return out


# ---------- 8 loop_repeticion ----------
def det_loop_repeticion(turns, bot):
    out, vistos = [], {}
    for t in turns:
        if t.rol != 'gabi' or is_nudge(t.texto):
            continue
        k = _norm(t.texto)
        if len(k) > 20 and k in vistos:
            out.append(_h('loop_repeticion', t, 'mensaje_repetido'))
        vistos[k] = t.idx
    for campo, rx in RE_FALTA.items():
        veces = [t for t in turns if t.rol == 'gabi' and rx.search(t.texto)]
        if len(veces) >= 3:
            out.append(_h('loop_repeticion', veces[2], 'campo_repreguntado_3x'))
    return out


# ---------- 9 duplicado_gabi ----------
def det_duplicado_gabi(turns, bot):
    out = []
    for a, b in zip(turns, turns[1:]):
        if a.rol == b.rol == 'gabi' and a.texto == b.texto:
            d = _dt(a, b)
            if d is not None and d < DUPLICADO_MAX_S:
                out.append(_h('duplicado_gabi', b))
    return out


# ---------- 10 plantilla_rota ----------
def det_plantilla_rota(turns, bot):
    return [_h('plantilla_rota', t) for t in turns if t.rol == 'gabi' and RE_PLANTILLA_ROTA.search(t.texto)]


# ---------- 11 hora_no_monotona ----------
def det_hora_no_monotona(turns, bot):
    out = []
    for a, b in zip(turns, turns[1:]):
        d = _dt(a, b)
        if d is not None and d < 0:
            out.append(_h('hora_no_monotona', b))
    return out


# ---------- 12 latencia_alta ----------
def det_latencia_alta(turns, bot):
    """Sólo opina si la línea de tiempo es monótona: hay conversaciones de varios periodos concatenadas
    (402 del bot A, 407 del B) donde los deltas entre turnos no significan nada."""
    if det_hora_no_monotona(turns, bot):
        return []
    out = []
    for a, b in zip(turns, turns[1:]):
        if a.rol == 'usuario' and b.rol == 'gabi' and not is_nudge(b.texto):
            d = _dt(a, b)
            if d is not None and d > LATENCIA_MAX_S:
                out.append(_h('latencia_alta', b, f'{int(d // 60)}min'))
    return out


# ---------- constantes de contenido ----------
# Calibradas contra los 17.490 turnos de usuario de la cohorte (jun-ago 2026). Lo que se vio:
#  - Los ADJUNTOS (foto, audio, PDF) NO dejan rastro en `messages`: no hay turnos vacíos ni marcadores
#    tipo [imagen]. Lo único observable es la UBICACIÓN compartida, que llega como URL de maps
#    (maps.app.goo.gl 90%, maps.google, maps.apple). Por eso `media_no_manejado` sólo mide ubicación.
#  - Esas URLs traen '?' en el query string (?g_st=aw): hay que quitarlas antes de buscar preguntas.
#  - 'll[aá]m' suelto matchea "un fraccionamiento que se llama igual": exigir formas imperativas.
#  - 'no tengo' suelto matchea "No tengo cochera" (un dato válido): exigir objeto de dato/desconocimiento.
#  - 'aprox' con número ('190 m2 aprox') es una respuesta usable, no una ambigüedad: los marcadores
#    débiles sólo cuentan cuando el turno no trae dígitos.
#  - Preguntas reales de 2 palabras son comunes ('Eres bot?', 'Se puede?', 'Hay cobertura ?'): no se
#    filtra por longitud sino excluyendo la respuesta numérica al bloque ('3?').
RE_URL = re.compile(r'https?://\S+|\bwww\.\S+')
RE_GUION_B = re.compile(
    r'Ya anot[ée]|Ya registr[ée]|¡Anotado|comp[áa]rteme la \*direcci[óo]n\*|Ahora ay[úu]dame con estos datos'
    r'|Solo me falta|necesitamos algunos datos del inmueble|casa o departamento', re.I)
# Sólo signo explícito: 'que'/'como' sueltos son pronombre relativo y conjunción ("la casa QUE compré",
# "COMO 80 m2"), no preguntas. Validación manual: matchear palabra interrogativa daba 0/15 de precisión.
RE_PREGUNTA = re.compile(r'[?¿]')
# Auto-respuestas de OTROS negocios (el teléfono no es del lead). Gabi las maneja bien; no son preguntas del usuario.
RE_AUTORESPUESTA = re.compile(
    r'gracias por (comunicarte|tu mensaje|escribirnos|preguntar)|horario de atenci[óo]n'
    r'|soy [^.\n]{2,40},? (tu|su) (mejor )?asesor|(tu|su) asesor(a)? (inmobiliari|de)|a su asesor'
    r'|en este momento no podemos responder|te atendemos|c[óo]mo podemos ayudarte|con quien tengo el gusto'
    r'|estoy lista para ayudarte|promociones [úu]nicas', re.I)
RE_SOLO_NUMERO = re.compile(r'^[\d\s.,$m²]*[?¿]+$')   # '3?' / '120?' : respuesta al bloque, no pregunta
RE_AMBIGUO_FUERTE = re.compile(
    r'(?<!\w)(no (lo |la |los |las )?s[ée]\b|no s[ée] |desconozco|no recuerdo|no estoy segur|ni idea'
    r'|no tengo (el |la |los |las |ese |esos |eso |idea|ni)|no (los |las |lo )?tengo a la mano'
    r'|no tengo esos? dato|no los tengo|a la mano)', re.I)
RE_AMBIGUO_DEBIL = re.compile(r'(?<!\w)(aprox\w*|m[áa]s o menos|creo que|depende|alrededor de|como unos?)', re.I)
RE_ACK = re.compile(r'^\W*(Perfecto|Gracias|Anotado|Excelente|Genial|Listo|Ya anot|Ya registr)', re.I)
RE_ACLARA = re.compile(r'falta|confirm|aclar|podr[íi]as (indicar|decir|compartir)|¿me (compartes|confirmas)|no (logr|pud)', re.I)
RE_BLOQUE = re.compile(r'\*antig[üu]edad\*', re.I)
# El dato SÓLO cuenta como "ya dado" si viene con cantidad. Validación manual (15 casos): sin exigir
# cantidad la precisión era 33% — "cochera", "área común de estacionamiento" o "3 cuartos solos" no dicen
# cuántos cajones/recámaras hay, y una dirección ("Coyoacán 372 ... Cp 03230") pasaba como precio.
_NUM = r'(?:\d+|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|medi[oa])'
CAMPOS_USUARIO = {
    'area':       re.compile(r'\d+\s*(m2|m²|mts?\b|metros)', re.I),
    # precio: moneda o magnitud pegada al número. 'valor ... 1' suelto daba falsos positivos
    # ('Cotizando valor / Es 1 planta baja'), igual que deudas ('Debo 7 mil de predial').
    'precio':     re.compile(r'\$\s?\d|\d[\d.,]*\s*(mill[óo]n|mdp)'
                             r'|(precio|valor|pido|pretendo|cuesta)\D{0,12}\$?\d{3}', re.I),
    'antiguedad': re.compile(r'\d+\s*a[ñn]os', re.I),
    'recamaras':  re.compile(_NUM + r'\s*(rec[áa]mara|habitaci|dormitorio)|sin\s+rec[áa]mara', re.I),
    'banos':      re.compile(_NUM + r'\s*(y\s+\w+\s+)?ba[ñn]o|sin\s+ba[ñn]o', re.I),
    'cajones':    re.compile(_NUM + r'\s*(caj[óo]n|caj[óo]nes|lugar(es)? de estacionamiento|cochera|garaje|garage)'
                             r'|sin\s+(caj[óo]n|caj[óo]nes|estacionamiento|cochera)|no (tiene|hay|cuenta con)\s+'
                             r'(caj[óo]n|caj[óo]nes|estacionamiento|cochera)', re.I),
}
RE_OPT_OUT = re.compile(
    r'(?<!\w)(ya (lo |la |se )?vend[ií]|ya no (me interesa|quiero|est[áa] en venta|lo vendo)|no me interesa'
    r'|no (quiero|deseo|pienso) vender|no quiero (nada|venderl)|dej(a|en|ame) de (escribir|molestar|mandar)'
    r'|no (me )?(escriban|molesten))', re.I)
RE_NUM_EQUIVOCADO = re.compile(
    r'(?<!\w)(n[úu]mero equivocado|est[áa]s? equivocad|estoy equivocad|no soy (el |la )?due'
    r'|no solicit[ée]|no ped[íi] nada|no inici[ée] nada|yo no (solicit|ped|inici))', re.I)
# 'me equivoqué' suelto NO va: en la validación manual 5 de 10 casos eran una corrección de dato
# ("Me equivoqué, la antigüedad es de 11 años"), que Gabi maneja bien.
RE_HUMANO = re.compile(
    r'(?<!\w)(hablar con (un|una|alguien)|quiero (un |una )?(asesor|ejecutiv|agente)|con un humano'
    r'|ll[áa]m(a|e|en)me|ll[áa]mame|me pueden llamar|que me llame|marcarme|contacto telef'
    r'|cu[áa]nto (me )?(dan|ofrecen|pagan|van a dar)|cu[áa]l es (la|su) oferta)', re.I)
# Cortesías que no son una respuesta pendiente: si el usuario sólo dice "ok/gracias/👍", ni el nudge ni
# la falta de respuesta de Gabi son un bug. Validación manual: sin este filtro, nudge_anomalo caía a 30%.
RE_MULETILLA_USUARIO = re.compile(
    r'^\W*(?:(?:ok+|okey|va|sale|listo|claro|gracias|mil|muchas|much[íi]simas|de acuerdo|entendido|s[íi]|no'
    r'|adi[óo]s|buen[oa]s?|d[íi]as|tardes|noches|hola|perfecto|excelente|un|momento|ahorita|perm[íi]teme'
    r'|por|favor|est[áa]|bien|dale|va+le)[\s\W]*)+$', re.I)
RE_MEDIA = re.compile(r'maps\.(app\.)?(goo|google|apple)|goo\.gl/maps|google\.com/maps', re.I)


def es_monotona(turns) -> bool:
    """True si las marcas de tiempo van hacia adelante. Cuando no lo son (11% del bot B, 72% del A: son
    conversaciones de varios periodos concatenadas), 'el siguiente turno de Gabi' NO es el siguiente turno
    real, y todo detector que mire la secuencia produce falsos positivos. Validación manual: 3 de 5
    hallazgos revisados de pregunta_ignorada eran ese artefacto."""
    return not det_hora_no_monotona(turns, None)


# Contextos que se PARECEN al dato pero no lo son (vistos en la validación manual de 30 casos):
# el área del TERRENO no es el área construida; 'años pagando' no es la antigüedad; una deuda de
# 'x mil de predial' no es el precio; 'medio baño' no responde cuántos baños completos hay.
_CONFUSIONES = {
    'area':       re.compile(r'terreno[^.\n]{0,60}|[^.\n]{0,30}de terreno', re.I),
    'antiguedad': re.compile(r'\d+\s*a[ñn]os\s+(pag|viviendo|habitando|casad|rentand)', re.I),
    'precio':     re.compile(r'(debo|deuda|adeudo|predial|infonavit|fovissste|cr[ée]dito)[^.\n]{0,40}', re.I),
    'banos':      re.compile(r'(1/2|medio|1\.5|y medio)\s*ba[ñn]o', re.I),
}


def _sin_confusiones(campo, texto):
    rx = _CONFUSIONES.get(campo)
    return rx.sub(' ', texto) if rx else texto


def _siguiente_gabi(turns, i):
    for t in turns[i + 1:]:
        if t.rol == 'gabi':
            return t
    return None


def _clasifica_respuesta_gabi(g):
    """'nudge' | 'guion' | 'libre' | None (sin respuesta)."""
    if g is None:
        return None
    if is_nudge(g.texto):
        return 'nudge'
    if RE_GUION_B.search(g.texto):
        return 'guion'
    return 'libre'


# ---------- 1 pregunta_ignorada ----------
def _gen_pregunta_ignorada(turns, bot):
    """El usuario pregunta y Gabi (a) manda el nudge o (b) REPITE un mensaje anterior en vez de responder.
    Validación manual: exigir que Gabi repita es lo único preciso. Gabi suele responder Y seguir el guion en
    el mismo mensaje, así que "responde con guion" por sí solo daba 0/15."""
    if not es_monotona(turns):
        return   # orden de turnos no confiable (ver es_monotona)
    for i, t in enumerate(turns):
        if t.rol != 'usuario':
            continue
        limpio = RE_URL.sub(' ', t.texto).strip()   # las URLs de maps traen '?' en el query string
        if (not limpio or RE_SOLO_NUMERO.match(limpio) or not RE_PREGUNTA.search(limpio)
                or RE_AUTORESPUESTA.search(limpio)):
            continue
        g = _siguiente_gabi(turns, i)
        if g is None:
            continue   # ya lo cubre silencio_bot
        if is_nudge(g.texto):
            yield _h('pregunta_ignorada', t, 'siguio_nudge')
            continue
        previos = {_norm(x.texto) for x in turns[:i] if x.rol == 'gabi' and not is_nudge(x.texto)}
        if _norm(g.texto) in previos:
            yield _h('pregunta_ignorada', t, 'repitio_mensaje_anterior')


# ---------- 2 ambigua_registrada ----------
def det_ambigua_registrada(turns, bot):
    if not es_monotona(turns):
        return []   # orden de turnos no confiable (ver es_monotona)
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario' or i == 0:
            continue
        g = _siguiente_gabi(turns, i)
        if g is None or is_nudge(g.texto) or not RE_ACK.search(g.texto) or RE_ACLARA.search(g.texto):
            continue   # Gabi no acusó recibo, o sí re-preguntó: no es el bug
        prev = turns[i - 1]
        tiene_num = bool(re.search(r'\d', t.texto))
        if RE_AMBIGUO_FUERTE.search(t.texto) or (RE_AMBIGUO_DEBIL.search(t.texto) and not tiene_num):
            out.append(_h('ambigua_registrada', t, 'marcador_ambiguo'))
        elif prev.rol == 'gabi' and RE_BLOQUE.search(prev.texto) and not tiene_num:
            out.append(_h('ambigua_registrada', t, 'sin_numeros'))
    return out


# ---------- 3 repregunta_dato_ya_dado ----------
def det_repregunta_dato_ya_dado(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'gabi':
            continue
        pedido = RE_MULETILLA.sub(' ', t.texto)
        for campo, rx in RE_FALTA.items():
            if not rx.search(pedido):
                continue
            # texto del usuario desde el último pedido de bloque hasta esta re-pregunta
            ini = max([j for j in range(i) if turns[j].rol == 'gabi' and RE_BLOQUE.search(turns[j].texto)] or [0])
            dicho = '\n'.join(x.texto for x in turns[ini:i] if x.rol == 'usuario')
            dicho = _sin_confusiones(campo, dicho)
            if CAMPOS_USUARIO[campo].search(dicho):
                out.append(_h('repregunta_dato_ya_dado', t, campo))
    return out


# ---------- 4 intencion_ignorada ----------
def det_intencion_ignorada(turns, bot):
    if not es_monotona(turns):
        return []   # orden de turnos no confiable (ver es_monotona)
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario':
            continue
        if RE_NUM_EQUIVOCADO.search(t.texto):
            sub = 'numero_equivocado'
        elif RE_OPT_OUT.search(t.texto):
            sub = 'opt_out'
        elif RE_HUMANO.search(t.texto):
            sub = 'pide_humano'
        else:
            continue
        if _clasifica_respuesta_gabi(_siguiente_gabi(turns, i)) in ('nudge', 'guion'):
            out.append(_h('intencion_ignorada', t, sub))
    return out


# ---------- 5 media_no_manejado ----------
def det_media_no_manejado(turns, bot):
    """Sólo mide UBICACIÓN compartida (URL de maps): los adjuntos no dejan rastro en `messages`."""
    if not es_monotona(turns):
        return []   # orden de turnos no confiable (ver es_monotona)
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario' or not RE_MEDIA.search(t.texto):
            continue
        if _clasifica_respuesta_gabi(_siguiente_gabi(turns, i)) in ('nudge', 'guion'):
            out.append(_h('media_no_manejado', t, 'ubicacion'))
    return out


def det_pregunta_ignorada(turns, bot):
    return list(_gen_pregunta_ignorada(turns, bot))


TODOS = [det_pregunta_ignorada, det_ambigua_registrada, det_repregunta_dato_ya_dado, det_intencion_ignorada,
         det_media_no_manejado, det_silencio_bot, det_nudge_anomalo, det_loop_repeticion, det_duplicado_gabi,
         det_plantilla_rota, det_hora_no_monotona, det_latencia_alta]
