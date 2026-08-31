"""Brand Lift de Meta para CO y MX.

⚠ Estas son cuentas publicitarias de PRODUCCIÓN. La cuota de API es por cuenta y agotarla
throttlea a cualquier otra integración que las consulte. Regla del cron: **una sola llamada por
país por corrida** — `fetch()` no pagina. El caché versionado en disco (`brand_lift_cache.json`)
es la fuente de verdad histórica; la API solo aporta lo nuevo que trae esa página, y tanto
`series()` como `merge_rows()` deduplican por (país, mes, pregunta, experiment_id), así que si un
estudio cerrado reaparece en la página no cuesta nada — se sobrescribe con el mismo dato.

`fetch()` devuelve `(ok, rows)`: el llamador (`build.py`) es quien decide qué hacer con un
refresco fallido — servir el caché como `stale` con el timestamp del último éxito real, nunca
disfrazarlo de refresco nuevo. Un éxito se persiste con `save_cache()`, fusionando sobre el caché
completo (`merge_rows`) para que ninguna fila se pierda cuando una página de 10 estudios deja
afuera algo que ya estaba guardado. El backfill histórico se corre a mano, nunca desde el cron.
"""
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

V = "v25.0"
ACCOUNTS = {"MX": "act_205661715114408", "CO": "act_770068953990542"}
FIELDS = ("id,name,type,start_time,end_time,results_first_available_date,"
          "objectives{id,name,type,is_primary,results}")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "brand_lift_cache.json")
QUESTIONS = os.path.join(HERE, "questions.json")


def _token():
    return os.environ.get("META_SYSTEM_USER_TOKEN") or os.environ.get("META_PCOM_TOKEN") or ""


# ── El mes de un estudio ───────────────────────────────────────────────────────
# Los estudios recurrentes arrancan el día 29 del mes que cubren. Febrero no tiene 29, así que
# el estudio "Feb-Mar" arranca el 1 de MARZO: leer el mes de `start_time` mandaba dos estudios
# al mismo mes calendario y hacía desaparecer febrero. Ocurrió en 2023-03, 2025-03 y 2026-03 de
# CO, y ahí las reglas de huella de `questions.json` comparan las 4 preguntas de un estudio
# contra las 4 del otro y se equivocan. El NOMBRE sí trae el mes sin ambigüedad
# ("Feb 2023-Mar 2023"), así que es la fuente correcta; `start_time` queda de respaldo para un
# nombre que no traiga mes reconocible.
_MESES = {m: i for i, m in enumerate(
    "ene feb mar abr may jun jul ago sep oct nov dic".split(), 1)}
_MESES.update({m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)})
_RE_MES = re.compile(r"([A-Za-zÁÉÍÓÚáéíóú]{3,10})\.?\s+(20\d\d)")


def study_month(study):
    """`YYYY-MM` del estudio. Del nombre si trae mes; si no, del `start_time`."""
    for txt, anio in _RE_MES.findall(study.get("name") or ""):
        n = _MESES.get(txt[:3].lower())
        if n:
            return f"{anio}-{n:02d}"   # el PRIMER mes del rango: el que el estudio cubre
    return (study.get("start_time") or "")[:7]


def parse_results(studies, country):
    """study → objective → experiment. `results` trae JSON serializado dentro de strings."""
    rows = []
    for s in studies:
        if s.get("type") != "LIFT":
            continue
        month = study_month(s)
        for o in ((s.get("objectives") or {}).get("data") or []):
            for raw in (o.get("results") or []):
                try:
                    r = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if r.get("experiment_id") is None:
                    continue
                rows.append({
                    "country": country, "month": month,
                    "study_id": s.get("id"), "study_name": s.get("name"),
                    "end_time": s.get("end_time"),
                    "experiment_id": str(r["experiment_id"]),
                    "question": None,          # lo asigna map_questions (Task 4b)
                    "exposed": r.get("scoreMean.test"),
                    "control": r.get("scoreMean.control"),
                    "lift": r.get("scoreMean.incremental"),
                    "ci_lower": r.get("brandLiftCILower"),
                    "ci_upper": r.get("brandLiftCIUpper"),
                    "responders_test": r.get("responders.test"),
                    "responders_control": r.get("responders.control"),
                    "confidence": r.get("breakthroughs.singleCellBayesianConfidence"),
                    "spend": r.get("spend"),
                    "benchmark_region": r.get("scoreMeanRegion"),
                    "benchmark_vertical": r.get("scoreMeanVertical"),
                })
    return rows


def _row_key(r):
    """Identidad de una fila para deduplicar: la misma que usa `series()` y `merge_rows()`."""
    return (r["country"], r["month"], r["question"], r["experiment_id"])


def _read_cache_file():
    if not os.path.exists(CACHE):
        return {}
    return json.loads(open(CACHE, encoding="utf-8").read())


def load_cache():
    return _read_cache_file().get("rows", [])


def load_last_refresh():
    """{"MX": iso_ts, "CO": iso_ts} — última vez que `fetch()` tuvo éxito para ese país.
    Vive junto a "rows" en el mismo archivo; separado de `load_cache()` para que ningún
    llamador existente de `load_cache()` tenga que enterarse de este campo nuevo."""
    return _read_cache_file().get("last_refresh", {})


def save_cache(rows, last_refresh):
    """Escribe `rows` + `last_refresh` de vuelta a `brand_lift_cache.json`. Solo se llama
    tras un refresco exitoso (`build.py` decide cuándo) — nunca a ciegas: si la API falla no
    hay nada nuevo que fusionar y el archivo se queda como está."""
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "last_refresh": last_refresh}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def merge_rows(cached, fresh):
    """Funde `fresh` (filas crudas de `fetch()`, sin mapear) dentro de `cached`, con la misma
    identidad que usa `series()`: (país, mes, pregunta, experiment_id). Un estudio que
    reaparece en la página se actualiza in place; uno nuevo se agrega. El caché **nunca se
    encoge**: toda fila que ya estaba y no vino en esta página se conserva tal cual."""
    acc = {_row_key(r): r for r in cached}
    for r in fresh:
        acc[_row_key(r)] = r
    return list(acc.values())


def _get(path, **params):
    params["access_token"] = _token()
    url = f"https://graph.facebook.com/{V}/{path.lstrip('/')}?{urlencode(params)}"
    try:
        with urlopen(url, timeout=120) as r:
            return True, json.loads(r.read())
    except HTTPError as e:
        try:
            return False, json.loads(e.read())
        except Exception:
            return False, {"error": {"code": e.code}}
    except (URLError, TimeoutError) as e:
        return False, {"error": {"message": str(e), "is_transient": True}}


def fetch(country):
    """Una llamada, un país, sin paginar. `limit=10` cubre el mes en curso y los anteriores.
    Devuelve `(ok, rows)`: `ok=False` ante cualquier error transitorio, con `rows=[]` — el
    llamador es quien decide cómo servir el caché existente cuando la API falla (nunca aquí:
    este módulo no vacía nada, solo informa honestamente si la llamada funcionó)."""
    ok, pl = _get(f"{ACCOUNTS[country]}/ad_studies", fields=FIELDS, limit=10)
    if not ok:
        err = pl.get("error") or {}
        print(f"WARN brand_lift {country}: {err.get('message')} "
              f"(transient={err.get('is_transient')}) — se conserva el caché")
        return False, []
    return True, parse_results(pl.get("data") or [], country)


def series(rows):
    """Una fila por (país, mes, pregunta). El más reciente gana si hay duplicados."""
    acc = {_row_key(r): r for r in rows}
    return [acc[k] for k in sorted(acc, key=lambda k: (k[0], k[1], str(k[2])))]


def load_questions():
    """{experiment_id: nombre_pregunta}. Se llena a mano al identificar cada firma.

    `questions.json` incluye una clave `_nota` con la procedencia del mapeo — no es un
    experiment_id, así que cualquier clave que empiece con `_` se descarta aquí para que
    nunca se cuele como fila mapeada (y para no tener que acordarse de filtrarla en cada
    llamador)."""
    if not os.path.exists(QUESTIONS):
        return {}
    raw = json.loads(open(QUESTIONS, encoding="utf-8").read())
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def map_questions(rows, mapping=None):
    """Etiqueta cada fila. Lo no identificado se marca, nunca se adivina: publicar una
    pregunta con el nombre equivocado es peor que no publicarla."""
    mapping = load_questions() if mapping is None else mapping
    for r in rows:
        r["question"] = mapping.get(r["experiment_id"], "sin_identificar")
    return rows


SIN_ID = ("sin_identificar_alta", "sin_identificar_baja")


def nombrar_sin_identificar(rows):
    """Le da un nombre POSICIONAL a las preguntas cuya etiqueta no se conoce, para poder
    dibujar su serie sin afirmar cuál pregunta es.

    El tablero explica cada hueco en vez de taparlo, y filtrar en silencio lo no identificado
    rompía esa regla: CO mostraba 2 filas cuando su estudio tiene 4 preguntas, sin decir en
    ninguna parte que faltaban dos. La posición es la tasa de expuestos DENTRO del mismo
    estudio (nunca del mes: dos estudios pueden caer en el mismo mes calendario). En los 46
    estudios de CO los dos rangos jamás se solapan —27.7-53.8% contra 9.1-18.6%— así que
    "alta" y "baja" señalan la misma pregunta todos los meses.

    Con una sola sin identificar no hay posición que distinguir: se deja anónima, y
    `publishable()` la sigue dejando afuera.
    """
    por_estudio = {}
    for r in rows:
        if r.get("question") == "sin_identificar":
            por_estudio.setdefault(r.get("study_id"), []).append(r)
    for rs in por_estudio.values():
        if len(rs) != 2:
            continue
        alta, baja = sorted(rs, key=lambda r: -(r.get("exposed") or 0))
        alta["question"], baja["question"] = SIN_ID
    return rows


def publishable(rows):
    """Solo lo identificado llega al tablero y al informe. Las posicionales sí pasan: llevan
    su propia advertencia y su serie es real; lo que no se afirma es qué pregunta son."""
    return [r for r in rows if r.get("question") not in (None, "sin_identificar")]
