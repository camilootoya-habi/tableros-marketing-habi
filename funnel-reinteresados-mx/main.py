"""Cloud Function (HTTP) que corre query.sql contra BigQuery y devuelve el JSON
del tablero reinteresados en vivo (~7 min de lag de hubspot.deals).
Fuente ÚNICA del SQL: query.sql (el mismo que usa el cron). Cache en memoria 60s.

Deploy (ver DEPLOY.md):
  gcloud functions deploy reinteresados-data --gen2 --runtime=python312 \
    --region=us-central1 --source=funnel-reinteresados-mx --entry-point=reinteresados \
    --trigger-http --allow-unauthenticated --service-account=<SA del cron> \
    --memory=512Mi --timeout=120s --project=<project>
"""
import json
import os
import time

import functions_framework
from google.cloud import bigquery

_CLIENT = bigquery.Client()
_SQL = open(os.path.join(os.path.dirname(__file__), "query.sql"), encoding="utf-8").read()
_TTL = 60  # seg de cache para no re-correr BQ en clics seguidos
_cache = {"ts": 0.0, "rows": None}

# Origen permitido (el tablero en GitHub Pages). Datos de solo lectura.
_ALLOW_ORIGIN = "https://camilootoya-habi.github.io"


def _cors(headers=None):
    h = {
        "Access-Control-Allow-Origin": _ALLOW_ORIGIN,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }
    if headers:
        h.update(headers)
    return h


@functions_framework.http
def reinteresados(request):
    if request.method == "OPTIONS":
        return ("", 204, _cors())
    now = time.time()
    force = request.args.get("force") == "1"
    if not force and _cache["rows"] is not None and (now - _cache["ts"]) < _TTL:
        rows = _cache["rows"]
    else:
        rows = [dict(r) for r in _CLIENT.query(_SQL).result()]
        _cache.update(ts=now, rows=rows)
    body = json.dumps(rows, default=str, ensure_ascii=False)
    return (body, 200, _cors({"Content-Type": "application/json; charset=utf-8",
                              "X-Generated-At": str(int(_cache["ts"]))}))
