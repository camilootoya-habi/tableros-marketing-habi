"""Convierte la conversación cruda de mabi_mx (texto con 'Gabi:'/'Usuario:' + 'HORA:') en turnos."""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

_SPLIT = re.compile(r'\n(?=Gabi:|Usuario:)')
_HORA = re.compile(r'HORA: ([\d\-T:.]+)')
_SUFIJO_HORA = re.compile(r'\.?\s*HORA: [\d\-T:.]+\s*$')
_NUDGE = re.compile(r'Sigo pendiente de tu respuesta', re.I)


@dataclass
class Turn:
    idx: int
    rol: str            # 'gabi' | 'usuario'
    texto: str
    hora: Optional[datetime]


def _parse_hora(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s.rstrip('.'))
    except ValueError:
        return None


def parse_turns(c: str) -> list[Turn]:
    turns = []
    for bloque in _SPLIT.split(c or ''):
        bloque = bloque.strip()
        if not bloque:
            continue
        m = _HORA.search(bloque)
        hora = _parse_hora(m.group(1)) if m else None
        texto = _SUFIJO_HORA.sub('', bloque).strip()
        rol, _, cuerpo = texto.partition(':')
        rol = rol.strip().lower()
        if rol not in ('gabi', 'usuario'):
            continue  # basura entre turnos: no la contamos como turno
        turns.append(Turn(len(turns), rol, cuerpo.strip(), hora))
    return turns


def is_nudge(texto: str) -> bool:
    return bool(_NUDGE.search(texto))


def redact(t: str) -> str:
    """Quita nombre del saludo, emails y teléfonos. Suficiente para muestras internas; NO anonimiza direcciones."""
    t = re.sub(r'¡?Hola,?\s+[^!\n*]{2,60}!', '¡Hola, [nombre]!', t)
    t = re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+', '[email]', t)
    t = re.sub(r'\+?\d[\d\s().-]{8,}\d',
               lambda m: '[tel]' if len(re.sub(r'\D', '', m.group())) >= 10 else m.group(), t)
    return t
