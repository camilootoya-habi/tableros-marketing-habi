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
        if t.rol != 'usuario':
            continue
        despues = turns[i + 1:]
        if not despues:
            out.append(_h('silencio_bot', t, 'sin_respuesta_final'))
        elif all(x.rol == 'gabi' and is_nudge(x.texto) for x in despues):
            out.append(_h('silencio_bot', t, 'solo_nudge'))
    return out


# ---------- 7 nudge_anomalo ----------
def det_nudge_anomalo(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'gabi' or not is_nudge(t.texto) or i == 0:
            continue
        prev = turns[i - 1]
        if prev.rol == 'usuario':
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
RE_PREGUNTA = re.compile(
    r'[?¿]|(?<!\w)(cu[áa]nto|cu[áa]ndo|c[óo]mo|qu[ée]|qui[ée]n|d[óo]nde|por qu[ée]|para qu[ée])(?!\w)', re.I)
RE_SOLO_NUMERO = re.compile(r'^[\d\s.,$m²]*[?¿]+$')   # '3?' / '120?' : respuesta al bloque, no pregunta
RE_AMBIGUO_FUERTE = re.compile(
    r'(?<!\w)(no (lo |la |los |las )?s[ée]\b|no s[ée] |desconozco|no recuerdo|no estoy segur|ni idea'
    r'|no tengo (el |la |los |las |ese |esos |eso |idea|ni)|no (los |las |lo )?tengo a la mano'
    r'|no tengo esos? dato|no los tengo|a la mano)', re.I)
RE_AMBIGUO_DEBIL = re.compile(r'(?<!\w)(aprox\w*|m[áa]s o menos|creo que|depende|alrededor de|como unos?)', re.I)
RE_ACK = re.compile(r'^\W*(Perfecto|Gracias|Anotado|Excelente|Genial|Listo|Ya anot|Ya registr)', re.I)
RE_ACLARA = re.compile(r'falta|confirm|aclar|podr[íi]as (indicar|decir|compartir)|¿me (compartes|confirmas)|no (logr|pud)', re.I)
RE_BLOQUE = re.compile(r'\*antig[üu]edad\*', re.I)
CAMPOS_USUARIO = {   # cómo se ve el dato cuando el usuario lo escribe
    'area':       re.compile(r'\d+\s*(m2|m²|mts?\b|metros)', re.I),
    'precio':     re.compile(r'\$\s?\d|\d[\d.,\s]{6,}\d|mill[óo]n|mdp|\b\d+\s*mil\b', re.I),
    'antiguedad': re.compile(r'\d+\s*a[ñn]os', re.I),
    'recamaras':  re.compile(r'rec[áa]mara|habitaci|cuarto|dormitorio', re.I),
    'banos':      re.compile(r'ba[ñn]o', re.I),
    'cajones':    re.compile(r'caj[óo]n|estacionamiento|cochera|garaje|garage', re.I),
}
RE_OPT_OUT = re.compile(
    r'(?<!\w)(ya (lo |la |se )?vend[ií]|ya no (me interesa|quiero|est[áa] en venta|lo vendo)|no me interesa'
    r'|no (quiero|deseo|pienso) vender|no quiero (nada|venderl)|dej(a|en|ame) de (escribir|molestar|mandar)'
    r'|no (me )?(escriban|molesten))', re.I)
RE_NUM_EQUIVOCADO = re.compile(
    r'(?<!\w)(n[úu]mero equivocado|est[áa]s? equivocad|estoy equivocad|me equivoqu[ée]|no soy (el |la )?due'
    r'|no solicit[ée]|no ped[íi] nada|no inici[ée] nada|yo no (solicit|ped|inici))', re.I)
RE_HUMANO = re.compile(
    r'(?<!\w)(hablar con (un|una|alguien)|quiero (un |una )?(asesor|ejecutiv|agente)|con un humano'
    r'|ll[áa]m(a|e|en)me|ll[áa]mame|me pueden llamar|que me llame|marcarme|contacto telef'
    r'|cu[áa]nto (me )?(dan|ofrecen|pagan|van a dar)|cu[áa]l es (la|su) oferta)', re.I)
RE_MEDIA = re.compile(r'maps\.(app\.)?(goo|google|apple)|goo\.gl/maps|google\.com/maps', re.I)


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
def det_pregunta_ignorada(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario':
            continue
        limpio = RE_URL.sub(' ', t.texto).strip()   # las URLs de maps traen '?' en el query string
        if not limpio or RE_SOLO_NUMERO.match(limpio) or not RE_PREGUNTA.search(limpio):
            continue
        r = _clasifica_respuesta_gabi(_siguiente_gabi(turns, i))
        if r is None:
            continue   # ya lo cubre silencio_bot
        if r == 'nudge':
            out.append(_h('pregunta_ignorada', t, 'siguio_nudge'))
        elif r == 'guion' and bot == 'B':
            out.append(_h('pregunta_ignorada', t, 'siguio_guion'))
        elif bot == 'A':
            out.append(_h('pregunta_ignorada', t, 'candidata_llm'))   # el LLM libre "responde" siempre: juzgar aparte
    return out


# ---------- 2 ambigua_registrada ----------
def det_ambigua_registrada(turns, bot):
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
        for campo, rx in RE_FALTA.items():
            if not rx.search(t.texto):
                continue
            # texto del usuario desde el último pedido de bloque hasta esta re-pregunta
            ini = max([j for j in range(i) if turns[j].rol == 'gabi' and RE_BLOQUE.search(turns[j].texto)] or [0])
            dicho = '\n'.join(x.texto for x in turns[ini:i] if x.rol == 'usuario')
            if CAMPOS_USUARIO[campo].search(dicho):
                out.append(_h('repregunta_dato_ya_dado', t, campo))
    return out


# ---------- 4 intencion_ignorada ----------
def det_intencion_ignorada(turns, bot):
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
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario' or not RE_MEDIA.search(t.texto):
            continue
        if _clasifica_respuesta_gabi(_siguiente_gabi(turns, i)) in ('nudge', 'guion'):
            out.append(_h('media_no_manejado', t, 'ubicacion'))
    return out


TODOS = [det_pregunta_ignorada, det_ambigua_registrada, det_repregunta_dato_ya_dado, det_intencion_ignorada,
         det_media_no_manejado, det_silencio_bot, det_nudge_anomalo, det_loop_repeticion, det_duplicado_gabi,
         det_plantilla_rota, det_hora_no_monotona, det_latencia_alta]
