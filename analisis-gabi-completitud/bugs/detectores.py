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
    out = []
    for a, b in zip(turns, turns[1:]):
        if a.rol == 'usuario' and b.rol == 'gabi' and not is_nudge(b.texto):
            d = _dt(a, b)
            if d is not None and d > LATENCIA_MAX_S:
                out.append(_h('latencia_alta', b, f'{int(d // 60)}min'))
    return out


TODOS = [det_silencio_bot, det_nudge_anomalo, det_loop_repeticion, det_duplicado_gabi,
         det_plantilla_rota, det_hora_no_monotona, det_latencia_alta]
