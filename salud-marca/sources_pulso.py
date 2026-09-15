"""Serie del agente encuestador de marca: Pulso Inmobiliario.

Pulso contacta por WhatsApp (y por un agente de voz) a dueños que publican
vivienda en propiedades.com y les pregunta por la categoría. Es la única
fuente de este tablero que le pregunta a gente que NO ha interactuado con
nosotros.

Se lee por su API pública de agregados: `GET /api/resultados?wave=`. No
lleva credenciales a propósito. Ese endpoint solo devuelve conteos, así que
por construcción no puede traer datos de personas — la encuesta es anónima y
el data.json de este hub se publica en GitHub Pages.

De cada ola sale una fila con el embudo de la marca focal: la conocen (Q3),
la considerarían (Q4) y sería su primera opción (Q5), más los atributos (Q7)
y el ranking de recordación espontánea (Q1).
"""
import json
import urllib.request

API = "https://pulso-inmobiliario.vercel.app/api/resultados"

# La marca del estudio y la marca de control. Pulso mete una marca inventada
# en la lista para medir cuánta gente dice que sí a todo: mezclarla con la
# competencia real haría leer "Vendecasa Express, 8%" como un competidor.
FOCAL = "tuhabi"
CONTROL = "fake"
# "Ninguna" viene como una barra más, pero no es una marca: es la gente que no
# reconoció ninguna de la lista. Entre Inmuebles24 y Lamudi se leería como un
# competidor, así que sale de la competencia y se publica como dato propio.
NINGUNA = "ninguna"

MAX_ESPONTANEA = 10


def fetch(wave=None, url=API, timeout=30):
    """Agregados de una ola. Sin `wave`, la ola activa. Lanza si la API falla."""
    destino = f"{url}?wave={wave}" if wave else url
    with urllib.request.urlopen(destino, timeout=timeout) as r:
        return json.load(r)


def _pct(bloque, brand_id):
    """El porcentaje de una marca en una pregunta de opciones. Ausente = 0.

    Una marca que nadie eligió no aparece en las barras, y eso es un cero
    medido, no un dato faltante: por eso 0 y no None.
    """
    for b in (bloque or {}).get("bars", []):
        if b.get("id") == brand_id:
            return b.get("pct", 0)
    return 0


def _competencia(q3):
    """Las demás marcas reales, sin la focal ni la de control."""
    return [{"marca": b["label"], "asistida_pct": b.get("pct", 0)}
            for b in (q3 or {}).get("bars", [])
            if b.get("id") not in (FOCAL, CONTROL, NINGUNA)]


def _atributos(q7):
    """Los atributos de la marca focal y sobre cuánta gente se promedian."""
    for fila in q7 or []:
        if fila.get("brand") == FOCAL:
            items = [{"id": i["id"], "text": i.get("text", ""), "avg": i.get("avg")}
                     for i in fila.get("items", [])]
            return items, fila.get("n", 0)
    return [], 0


def fila(payload):
    """Una ola de Pulso → una fila de la serie."""
    atributos, atributos_n = _atributos(payload.get("q7"))
    totals = payload.get("totals") or {}
    return {
        "wave": payload.get("wave_id"),
        "respuestas": totals.get("completed", 0),
        "asistida_pct": _pct(payload.get("q3"), FOCAL),
        "consideracion_pct": _pct(payload.get("q4"), FOCAL),
        "primera_opcion_pct": _pct(payload.get("q5"), FOCAL),
        "ruido_pct": _pct(payload.get("q3"), CONTROL),
        "ninguna_pct": _pct(payload.get("q3"), NINGUNA),
        "competencia": _competencia(payload.get("q3")),
        # Se transcribe el ranking tal cual. Pulso agrupa las respuestas
        # abiertas por ortografía y NO interpreta: una variante mal escrita
        # es su propio grupo. Codificar marcas acá rompería ese criterio y
        # además lo haría a ciegas, lejos del dato crudo.
        "espontanea": [{"texto": i["text"], "n": i["count"]}
                       for i in (payload.get("q1") or {}).get("items", [])[:MAX_ESPONTANEA]],
        "atributos": atributos,
        "atributos_n": atributos_n,
    }


def series(payloads):
    """Varias olas → la serie ordenada cronológicamente por id de ola."""
    return sorted((fila(p) for p in payloads), key=lambda f: f["wave"] or "")
