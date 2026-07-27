"""Brand Lift de Meta para CO y MX.

⚠ Estas son cuentas publicitarias de PRODUCCIÓN. La cuota de API es por cuenta y agotarla
throttlea a cualquier otra integración que las consulte. Regla del cron: **una sola llamada por
país por corrida** — `fetch()` no pagina. El caché versionado en disco (`brand_lift_cache.json`)
es la fuente de verdad histórica; la API solo aporta lo nuevo que trae esa página, y `series()`
deduplica por (país, mes, pregunta, experiment_id), así que si un estudio cerrado reaparece en la
página no cuesta nada — se sobrescribe con el mismo dato. Al primer error transitorio se
imprime la advertencia y se devuelve lo que haya (nada), conservando el caché existente en disco.
El backfill histórico se corre a mano, nunca desde el cron.
"""
import json
import os
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


def parse_results(studies, country):
    """study → objective → experiment. `results` trae JSON serializado dentro de strings."""
    rows = []
    for s in studies:
        if s.get("type") != "LIFT":
            continue
        month = (s.get("start_time") or "")[:7]
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


def load_cache():
    if not os.path.exists(CACHE):
        return []
    return json.loads(open(CACHE, encoding="utf-8").read()).get("rows", [])


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
    Ante cualquier error transitorio se conserva el caché: nunca se vacía la serie por un rate
    limit."""
    ok, pl = _get(f"{ACCOUNTS[country]}/ad_studies", fields=FIELDS, limit=10)
    if not ok:
        err = pl.get("error") or {}
        print(f"WARN brand_lift {country}: {err.get('message')} "
              f"(transient={err.get('is_transient')}) — se conserva el caché")
        return []
    return parse_results(pl.get("data") or [], country)


def series(rows):
    """Una fila por (país, mes, pregunta). El más reciente gana si hay duplicados."""
    acc = {}
    for r in rows:
        acc[(r["country"], r["month"], r["question"], r["experiment_id"])] = r
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


def publishable(rows):
    """Solo lo identificado llega al tablero y al informe."""
    return [r for r in rows if r.get("question") not in (None, "sin_identificar")]
