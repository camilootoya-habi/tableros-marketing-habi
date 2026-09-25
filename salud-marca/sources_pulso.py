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
import re
import unicodedata
import urllib.parse
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


#: La encuesta se manda a dos públicos: dueños que publican su vivienda y
#: agentes inmobiliarios independientes (brokers). Sin pedir audiencia la API
#: devuelve los dos mezclados, así que siempre se pide uno. Se publican los dos
#: por separado y el tablero elige cuál mostrar: la salud de marca se lee sobre
#: los dueños, que son el cliente de TuHabi, y el de brokers va aparte porque
#: son el canal y conocen la categoría de otra forma.
AUDIENCIA = "owner"
AUDIENCIAS = ("owner", "broker")


def fetch(wave=None, url=API, timeout=30, audiencia=AUDIENCIA):
    """Agregados de una ola y un público. Sin `wave`, la ola activa.

    Lanza si la API falla.
    """
    params = {"audience": audiencia}
    if wave:
        params["wave"] = wave
    destino = f"{url}?{urllib.parse.urlencode(params)}"
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


# ── Agrupación de las preguntas abiertas ─────────────────────────────────────
# Q1 y Q2 son MARCAS escritas a mano: la misma marca llega como "Inmuebles 24",
# "inmuebles24", "I24" o "Inmuebkes 24". Se normaliza (minúsculas, sin acentos ni
# espacios) y se junta con esta tabla de variantes. Una respuesta que nombra varias
# marcas suma una mención a cada una. Lo que no está en la tabla queda como su
# propio grupo con el texto original: se agrupa, no se descarta ni se adivina.
MARCAS = {
    "Inmuebles24": ["inmuebles24", "inmueblesveinticuatro", "inmueble24", "inmiebles24",
                    "inmuebkes24", "ibmuwbles24", "i24"],
    "EasyBroker": ["easybroker", "esaybroker", "easyboker", "easybrocker"],
    "Vivanuncios": ["vivanuncios", "vivaanuncios", "vivaanncios"],
    "Propiedades.com": ["propiedades", "propiesdes", "propiedadescom"],
    "Mercado Libre": ["mercadolibre"],
    "Lamudi": ["lamudi"],
    "TuHabi": ["tuhabi"],
    "Nocnok": ["nocnok", "nocknok", "nocknock", "nocnoc", "noknok"],
    "Facebook / Marketplace": ["facebook", "marketplace", "marquetplace", "markeplace"],
    "Instagram": ["instagram", "ig"],
    "Century 21": ["century"],
    "Proppit": ["proppit", "propit"],
    "Pincali": ["pincali"],
    "Remax": ["remax"],
    "Tecnocasa": ["tecnocasa"],
    "Metros Cúbicos": ["metroscubicos"],
    "Ninguna / no recuerda": ["ninguna", "nada", "norecuerdo"],
}
# Las variantes de 1-3 letras ("ig", "i24") solo cuentan si son la respuesta
# entera: como fragmento aparecen dentro de cualquier palabra.
_CORTA = 3


def _norm(texto):
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t)


def _marcas_en(texto):
    n = _norm(texto)
    halladas = [m for m, alias in MARCAS.items()
                if any((a == n) if len(a) <= _CORTA else (a in n) for a in alias)]
    # "Ninguna" no se suma a una respuesta que sí nombró marcas ("No recuerdo propiedades.com").
    if len(halladas) > 1 and "Ninguna / no recuerda" in halladas:
        halladas.remove("Ninguna / no recuerda")
    return halladas


def agrupar_marcas(respuestas):
    """[(texto, veces)] → [{grupo, n}] de mayor a menor."""
    cuenta, etiqueta = {}, {}
    for texto, veces in respuestas:
        texto = (texto or "").strip()
        if not texto:
            continue
        for g in (_marcas_en(texto) or [None]):
            clave = g or _norm(texto)
            etiqueta.setdefault(clave, g or texto)
            cuenta[clave] = cuenta.get(clave, 0) + veces
    return [{"grupo": etiqueta[k], "n": v}
            for k, v in sorted(cuenta.items(), key=lambda kv: (-kv[1], etiqueta[kv[0]]))]


# Q8 es una opinión en frase libre ("compran barato para vender caro"), no una
# marca. Se agrupa por TEMA con palabras clave, en este orden: gana el primero
# que coincide. Por eso "negativa" va antes que "compran": "compran barato para
# vender caro" es una queja, no una descripción del servicio.
TEMAS_Q8 = [
    ("Opinión negativa", r"incumpl|abusiv|etic|complicad|pesim|perder el tiempo|"
                         r"barato para vender caro|innecesari|no estaban"),
    ("No la conoce / sin opinión", r"no la conozco|no me refiere|no me interesa"),
    ("Publicidad o logo", r"comercial|regil|anuncio|logo"),
    ("Vivienda de bajo costo", r"bajo|vajo|interes social|medio bajo"),
    ("Opinión positiva", r"mejor|confianza|buena|excelente"),
    ("Compran tu casa", r"compra|compran|vonora"),
    ("Venta de casas", r"venta|vender|vende"),
    ("Inmobiliaria / plataforma", r"inmobiliari|plataforma|portal|pagina|buscador|constructora|conectand"),
    ("Casas / vivienda", r"casa|vivienda"),
]


def agrupar_temas(textos):
    """[texto] → [{grupo, n, ejemplo}] de mayor a menor. `ejemplo` es la respuesta
    más corta del grupo, para que el tema se lea con palabras de la gente."""
    grupos = {}
    for texto in textos:
        t = unicodedata.normalize("NFKD", texto.lower())
        t = "".join(c for c in t if not unicodedata.combining(c))
        g = next((nombre for nombre, rx in TEMAS_Q8 if re.search(rx, t)), "Otras")
        grupos.setdefault(g, []).append(texto.strip())
    return [{"grupo": g, "n": len(v), "ejemplo": min(v, key=len)}
            for g, v in sorted(grupos.items(), key=lambda kv: (-len(kv[1]), kv[0] == "Otras", kv[0]))]


def _barras(bloque):
    return [{"id": b.get("id"), "label": b.get("label", ""), "n": b.get("count", 0),
             "pct": b.get("pct", 0)} for b in (bloque or {}).get("bars", [])]


def _textos(bloque):
    # Pulso ya las publica en su página de resultados (las más recientes, sin
    # datos de quién respondió). Se transcriben tal cual; el tablero las escapa.
    return [t for t in (bloque or {}).get("texts", []) if isinstance(t, str)]


def _preguntas(payload):
    """Cada pregunta de la encuesta con su resultado completo, para el tablero
    pregunta por pregunta. Las claves son las de Pulso (q1..q8; no hay q6)."""
    q = lambda k: payload.get(k) or {}
    q2 = _textos(q("q2"))
    q8 = _textos(q("q8"))
    return {
        "q1": {"grupos": agrupar_marcas((i["text"], i["count"]) for i in q("q1").get("items", [])),
               "total": q("q1").get("total", 0)},
        # Q2 admite varias marcas por respuesta, así que los grupos cuentan MENCIONES.
        # Pulso publica solo las respuestas más recientes: `muestra` dice sobre cuántas.
        "q2": {"grupos": agrupar_marcas((t, 1) for t in q2), "muestra": len(q2),
               "ninguna": q("q2").get("none_count", 0), "total": q("q2").get("total", 0)},
        "q3": {"barras": _barras(q("q3")), "total": q("q3").get("total", 0)},
        "q4": {"barras": _barras(q("q4")), "total": q("q4").get("total", 0)},
        "q5": {"barras": _barras(q("q5")), "total": q("q5").get("total", 0)},
        "q7": [{"marca": f.get("brand"), "label": f.get("label", ""), "n": f.get("n", 0),
                "ns": f.get("ns", 0),
                "items": [{"id": i["id"], "text": i.get("text", ""), "avg": i.get("avg")}
                          for i in f.get("items", [])]}
               for f in (payload.get("q7") or [])],
        "q8": {"grupos": agrupar_temas(q8), "muestra": len(q8), "total": q("q8").get("total", 0)},
    }


def fila(payload):
    """Una ola de Pulso → una fila de la serie."""
    atributos, atributos_n = _atributos(payload.get("q7"))
    calidad = payload.get("quality") or {}
    totals = payload.get("totals") or {}
    return {
        "audiencia": payload.get("audience"),
        "wave": payload.get("wave_id"),
        "respuestas": totals.get("completed", 0),
        "asistida_pct": _pct(payload.get("q3"), FOCAL),
        "consideracion_pct": _pct(payload.get("q4"), FOCAL),
        "primera_opcion_pct": _pct(payload.get("q5"), FOCAL),
        "ruido_pct": _pct(payload.get("q3"), CONTROL),
        "ninguna_pct": _pct(payload.get("q3"), NINGUNA),
        "competencia": _competencia(payload.get("q3")),
        # Agrupada igual que Q1 en el pregunta por pregunta (ver MARCAS): si las dos
        # vistas usaran criterios distintos, "Inmuebles24" tendría dos cifras.
        "espontanea": [{"texto": g["grupo"], "n": g["n"]}
                       for g in agrupar_marcas((i["text"], i["count"])
                                               for i in (payload.get("q1") or {}).get("items", []))
                       ][:MAX_ESPONTANEA],
        "atributos": atributos,
        "atributos_n": atributos_n,
        "excluidas": calidad.get("excluded", 0),
        "excluidas_pct": calidad.get("excluded_pct", 0),
        "preguntas": _preguntas(payload),
    }


def series(payloads):
    """Varias olas y públicos → la serie ordenada por ola y, dentro, por público."""
    return sorted((fila(p) for p in payloads),
                  key=lambda f: (f["wave"] or "", f["audiencia"] or ""))
