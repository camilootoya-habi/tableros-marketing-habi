# Tablero de Marca + generador de informes de campaña — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un tablero vivo de indicadores de marca (Brand Lift CO+MX, tráfico y exit poll MX) que además sirve de fuente de datos para generar informes de campaña mensuales congelados, empezando por el de Uber OOH.

**Architecture:** `marca-mx/build.py` corre tres drivers independientes y escribe un `data.json` con un `status` explícito por métrica × país. `informe-uber-ooh/build.py` mezcla capítulos editoriales en Markdown con ese `data.json` y renderiza la edición del mes en curso; las ediciones de meses cerrados no se vuelven a tocar.

**Tech Stack:** Python 3 **stdlib únicamente** (`urllib`, `subprocess`, `json`, `re`), `bq` CLI, Chart.js por CDN, GitHub Actions.

Spec: `docs/superpowers/specs/2026-07-27-tablero-marca-mx-design.md`

## Global Constraints

- **Solo stdlib en todo lo que corre en el cron.** El workflow `update-data.yml` no tiene `setup-python` ni `pip install`. Nada de `requests`, `pyyaml`, `pandas`. BigQuery se consulta con `subprocess` sobre `bq` (patrón de `marketing-loop/build_data.py`), Meta con `urllib.request`.
- **Contenido editorial en Markdown, un archivo por capítulo.** No YAML (dependencia no garantizada) y no JSON (imposible escribir prosa larga).
- **Reglas de la cuenta publicitaria de Meta, no negociables.** Techo duro de llamadas por corrida; persistir la respuesta cruda a disco antes de parsearla; nunca re-consultar un estudio con `end_time` pasado; abortar al primer `is_transient` conservando el caché; backfill histórico solo a mano y supervisado, nunca desde el cron. Cuentas: `act_205661715114408` (MX), `act_770068953990542` (CO) — producción.
- **`index.html` de la raíz es generado.** Nunca editarlo a mano; `scripts/build_hub.py` lo regenera desde los `meta.json`.
- **Gráficas con Chart.js por CDN**, usando el helper `mkChart` de `scripts/templates/dashboard.html`. No SVG a mano.
- **Revisión en `localhost:8091` antes de cualquier push.** Commit y push solo al final, con visto bueno.
- **Tema visual**: fondo `#0f172a`, cards `#1e293b`, bordes `#334155`, acento `#818cf8`, texto `#f8fafc` / `#e2e8f0` / `#94a3b8`.
- **Tests con pytest, locales.** El repo no tiene suite ni step de CI; los tests son para el ciclo del desarrollador y cubren lógica pura (parseo, merge, interpolación, mapeo de plazas). Las llamadas a `bq` y a Meta se verifican con corridas manuales documentadas, no se mockean.
- **Plazas**: MTY = `Nuevo Leon`/`Nuevo León`, GDL = `Jalisco`, CDMX, Resto. Cubrir siempre la variante sin tilde.

---

## Contrato de `data.json` (lo consumen el tablero y el informe)

Todas las tareas dependen de esta forma. `status` ∈ `ok` | `not_available` | `stale` | `error`.

```json
{
  "generated_at": "2026-07-27T18:00:00Z",
  "metrics": {
    "brand_lift": {
      "MX": {"status": "ok", "source": "api", "last_updated": "2026-07-27T18:00:00Z",
             "series": [{"month": "2026-07", "question": "ad_recall", "exposed": 0.284,
                         "control": 0.332, "lift": -0.048, "ci_lower": -0.0896,
                         "ci_upper": -0.0021, "responders_test": 689,
                         "responders_control": 676, "confidence": 0.05,
                         "benchmark_region": 0.0102, "experiment_id": "1380313597249074"}]},
      "CO": {"status": "ok", "source": "api", "last_updated": "...", "series": []}
    },
    "traffic": {
      "MX": {"status": "ok", "source": "bq", "last_updated": "...",
             "series": [{"month": "2026-07", "plaza": "MTY", "users": 12345,
                          "spend": 343635.0, "cpv": 27.83}]},
      "CO": {"status": "not_available",
             "reason": "Sin export de GA4 usable para CO. El tráfico de CO se mide por Segment en el WBR 2.0."}
    },
    "exit_poll": {
      "MX": {"status": "ok", "source": "bq", "last_updated": "...",
             "series": [{"month": "2026-07", "plaza": "MTY", "registros_web": 1132,
                          "respuestas": 800, "tasa": 0.707,
                          "opciones": {"Publicidad en branding de coches de UBER": 29}}]},
      "CO": {"status": "not_available",
             "reason": "El exit poll de CO vive en habi_db.tabla_contacto_v2.fuente_conocio_habi, con otro esquema. Pendiente de mapear."}
    }
  }
}
```

`not_available` con `reason` es el mecanismo del estado vacío explícito de CO. **Nunca** una serie en cero para representar "sin fuente".

---

# FASE 1 — Datos

### Task 1: Esqueleto de `marca-mx` y contrato de `data.json`

**Files:**
- Create: `marca-mx/meta.json`
- Create: `marca-mx/build.py`
- Create: `marca-mx/contract.py`
- Test: `marca-mx/tests/test_contract.py`

**Interfaces:**
- Produces: `contract.py::metric(status, source=None, series=None, reason=None) -> dict`,
  `contract.py::envelope(metrics: dict, now: str) -> dict`,
  `contract.py::NOT_AVAILABLE` (dict de razones por métrica y país).

- [ ] **Step 1: Write the failing test**

```python
# marca-mx/tests/test_contract.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import contract

def test_metric_ok_lleva_source_y_serie():
    m = contract.metric("ok", source="bq", series=[{"month": "2026-07"}])
    assert m["status"] == "ok" and m["source"] == "bq" and len(m["series"]) == 1
    assert "reason" not in m

def test_metric_not_available_exige_razon_y_no_trae_serie_en_cero():
    m = contract.metric("not_available", reason="Sin export de GA4 usable para CO.")
    assert m["status"] == "not_available"
    assert m["reason"].endswith(".")
    assert m.get("series") in (None, [])   # jamás una serie de ceros

def test_metric_not_available_sin_razon_es_error():
    try:
        contract.metric("not_available")
    except ValueError as e:
        assert "reason" in str(e)
    else:
        raise AssertionError("debió exigir reason")

def test_envelope_arma_las_tres_metricas_por_pais():
    env = contract.envelope({"brand_lift": {"MX": contract.metric("ok", source="api", series=[])}},
                            now="2026-07-27T18:00:00Z")
    assert env["generated_at"] == "2026-07-27T18:00:00Z"
    assert env["metrics"]["brand_lift"]["MX"]["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd marca-mx && python3 -m pytest tests/test_contract.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'contract'`

- [ ] **Step 3: Write minimal implementation**

```python
# marca-mx/contract.py
"""Forma de data.json. Un status explícito por métrica × país: 'not_available' con su
razón es lo que hace visible que a CO le faltan fuentes, en vez de mostrar ceros."""

VALID = ("ok", "not_available", "stale", "error")

NOT_AVAILABLE = {
    ("traffic", "CO"): "Sin export de GA4 usable para CO. El tráfico de CO se mide por Segment en el WBR 2.0.",
    ("exit_poll", "CO"): "El exit poll de CO vive en habi_db.tabla_contacto_v2.fuente_conocio_habi, con otro esquema. Pendiente de mapear.",
}


def metric(status, source=None, series=None, reason=None, last_updated=None):
    if status not in VALID:
        raise ValueError(f"status inválido: {status} (válidos: {VALID})")
    if status in ("not_available", "error") and not reason:
        raise ValueError(f"status={status} exige reason explícita")
    out = {"status": status}
    if source:
        out["source"] = source
    if last_updated:
        out["last_updated"] = last_updated
    if reason:
        out["reason"] = reason
    # `stale` conserva su serie: si la API de Meta falla varios días, el driver sirve el
    # caché y last_updated envejece — es justo cuando el histórico debe seguir dibujándose,
    # con el badge de vencido. `not_available` y `error` NO llevan serie, a propósito.
    if status in ("ok", "stale"):
        out["series"] = series or []
    return out


def envelope(metrics, now):
    return {"generated_at": now, "metrics": metrics}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd marca-mx && python3 -m pytest tests/test_contract.py -v`
Expected: 4 passed

- [ ] **Step 5: Crear `meta.json`**

```json
{
  "title": "Marca — Brand Lift, tráfico y atribución declarada",
  "description": "Indicadores de marca: Brand Lift de Meta (CO+MX), tráfico y CPV por plaza, y atribución declarada del exit poll (MX).",
  "country": "MX & CO",
  "section": "dashboard",
  "order": 20,
  "maximum_bytes_billed": 20000000000
}
```

Sin campo `query`: el cron lo corre por `build.py` (auto-discovery en `scripts/run_queries.py`).

- [ ] **Step 6: Commit**

```bash
git add marca-mx/meta.json marca-mx/contract.py marca-mx/tests/test_contract.py
git commit -m "feat(marca): contrato de data.json con status por metrica y pais"
```

---

### Task 2: Query y driver del exit poll (MX)

**Files:**
- Create: `marca-mx/queries/exit_poll.sql`
- Create: `marca-mx/sources_bq.py`
- Test: `marca-mx/tests/test_exit_poll.py`

**Interfaces:**
- Consumes: `contract.metric`
- Produces: `sources_bq.py::run_query(sql_path: str) -> list[dict]`,
  `sources_bq.py::exit_poll_series(rows: list[dict]) -> list[dict]`

El mapeo de plazas vive en el `CASE` de cada query, **no** en un diccionario de Python. Las tres
fuentes nombran las plazas en su propio vocabulario — `estado_mexico`, `geo.region` y
`area_metropolitana` — así que un solo diccionario no puede servirlas, y una copia en Python de una
de ellas se desincroniza el día que alguien edite el SQL y no el diccionario.

- [ ] **Step 1: Escribir la query**

```sql
-- marca-mx/queries/exit_poll.sql
-- Exit poll "¿Dónde nos conociste?" MX. Denominador = registros WEB (fuente_id=3):
-- es el único que reproduce la tasa de respuesta de 71-79% del informe original.
SELECT
  FORMAT_DATE('%Y-%m', DATE(fecha_creacion)) AS month,
  CASE
    WHEN estado_mexico IN ('Nuevo Leon', 'Nuevo León') THEN 'MTY'
    WHEN estado_mexico = 'Jalisco'                     THEN 'GDL'
    WHEN estado_mexico IN ('Ciudad de Mexico', 'Ciudad de México',
                           'Distrito Federal', 'Estado de Mexico',
                           'Estado de México', 'Mexico', 'México') THEN 'CDMX'
    ELSE 'Resto'
  END AS plaza,
  donde_nos_conociste AS opcion,
  COUNT(*) AS registros_web
FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general`
WHERE fuente_id = 3
  AND DATE(fecha_creacion) >= '2022-01-01'
  AND DATE(fecha_creacion) < DATE_TRUNC(CURRENT_DATE(), MONTH) + INTERVAL 1 MONTH
GROUP BY 1, 2, 3
```

`opcion` viene NULL para quien no respondió: esa fila es el complemento del denominador, no se descarta.

- [ ] **Step 2: Write the failing test**

```python
# marca-mx/tests/test_exit_poll.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_bq

ROWS = [
    {"month": "2026-03", "plaza": "MTY", "opcion": None, "registros_web": "200"},
    {"month": "2026-03", "plaza": "MTY", "opcion": "Publicidad en branding de coches de UBER", "registros_web": "28"},
    {"month": "2026-03", "plaza": "MTY", "opcion": "Google", "registros_web": "572"},
]

def test_tasa_de_respuesta_excluye_los_nulos_del_numerador():
    s = sources_bq.exit_poll_series(ROWS)
    fila = [f for f in s if f["plaza"] == "MTY"][0]
    assert fila["registros_web"] == 800          # 200 + 28 + 572
    assert fila["respuestas"] == 600             # solo los que respondieron
    assert round(fila["tasa"], 4) == 0.75

def test_opciones_no_incluye_la_llave_nula():
    fila = sources_bq.exit_poll_series(ROWS)[0]
    assert None not in fila["opciones"]
    assert fila["opciones"]["Publicidad en branding de coches de UBER"] == 28

def test_serie_ordenada_por_mes_y_plaza():
    rows = ROWS + [{"month": "2026-01", "plaza": "GDL", "opcion": "Google", "registros_web": "10"}]
    s = sources_bq.exit_poll_series(rows)
    assert [(f["month"], f["plaza"]) for f in s] == [("2026-01", "GDL"), ("2026-03", "MTY")]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd marca-mx && python3 -m pytest tests/test_exit_poll.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'sources_bq'`

- [ ] **Step 4: Write minimal implementation**

```python
# marca-mx/sources_bq.py
"""Consultas a BigQuery. `bq` por subprocess, patrón de marketing-loop/build_data.py.
bq devuelve todos los números como string: convertir aquí, no en el HTML."""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def run_query(sql_path, max_bytes=20_000_000_000):
    sql = open(os.path.join(HERE, sql_path), encoding="utf-8").read()
    out = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json",
         "--max_rows=100000", f"--maximum_bytes_billed={max_bytes}"],
        input=sql, capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        raise RuntimeError(f"bq falló en {sql_path}: {out.stderr.strip()[:400]}")
    return json.loads(out.stdout or "[]")


def exit_poll_series(rows):
    """Agrupa (mes, plaza): registros WEB totales, respuestas, tasa y conteo por opción."""
    acc = {}
    for r in rows:
        k = (r["month"], r["plaza"])
        a = acc.setdefault(k, {"month": r["month"], "plaza": r["plaza"],
                               "registros_web": 0, "respuestas": 0, "opciones": {}})
        n = int(r["registros_web"])
        a["registros_web"] += n
        opcion = (r.get("opcion") or "").strip()
        if opcion:
            a["respuestas"] += n
            a["opciones"][opcion] = a["opciones"].get(opcion, 0) + n
    for a in acc.values():
        a["tasa"] = a["respuestas"] / a["registros_web"] if a["registros_web"] else 0.0
    return [acc[k] for k in sorted(acc)]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd marca-mx && python3 -m pytest tests/test_exit_poll.py -v`
Expected: 3 passed

- [ ] **Step 6: Verificación contra datos reales**

```bash
cd marca-mx && python3 -c "
import sources_bq, json
s = sources_bq.exit_poll_series(sources_bq.run_query('queries/exit_poll.sql'))
nac = {}
for f in s:
    a = nac.setdefault(f['month'], {'r': 0, 'w': 0, 'u': 0})
    a['r'] += f['respuestas']; a['w'] += f['registros_web']
    a['u'] += sum(v for k, v in f['opciones'].items() if 'UBER' in k.upper())
for m in sorted(nac)[-10:]:
    a = nac[m]
    print(m, f\"tasa={100*a['r']/a['w']:.1f}% uber={a['u']} share={100*a['u']/a['r']:.2f}%\")
"
```

Expected — debe reproducir la tabla de evidencia del spec: tasa entre 62% y 79%, y share nacional de Uber 0.21% (nov-25) → 1.83% (jul-26). **Si la tasa sale ~20%, el filtro `fuente_id = 3` se perdió.**

- [ ] **Step 7: Commit**

```bash
git add marca-mx/queries/exit_poll.sql marca-mx/sources_bq.py marca-mx/tests/test_exit_poll.py
git commit -m "feat(marca): exit poll MX por mes y plaza con denominador WEB"
```

---

### Task 3: Query y driver de tráfico + CPV por plaza (MX)

**Files:**
- Create: `marca-mx/queries/trafico_plazas.sql`
- Modify: `marca-mx/sources_bq.py` (agregar `traffic_series`)
- Test: `marca-mx/tests/test_trafico.py`

**Interfaces:**
- Produces: `sources_bq.py::traffic_series(rows: list[dict]) -> list[dict]` con llaves
  `month, plaza, users, spend, cpv`

**Contexto crítico:** las tablas `papyrus-data-mx.habi_wh_bi.resumen_inversiones_region_mx`,
`facebook_region_mx` y `google_region_mx` **están muertas** (cortan en 2024-04-25) y devuelven cero
filas sin error. La fuente viva es `sellers-main-prod.bi_mx.resumen_inversiones_regiones_mexico`
(mensual, columnas `mes`, `area_metropolitana`, `spend`).

- [ ] **Step 1: Escribir la query**

```sql
-- marca-mx/queries/trafico_plazas.sql
-- Usuarios activos GA4 por plaza × mes, cruzados con inversión mensual por área metropolitana.
-- CPV es mensual por diseño: la tabla de inversión no tiene granularidad diaria.
-- CDMX: GA4 separa CDMX de Estado de México, pero la inversión los agrupa en "Valle de México";
-- por eso el lado de GA4 también los une, o el CPV de CDMX saldría inflado.
WITH ga AS (
  SELECT
    FORMAT_DATE('%Y-%m', PARSE_DATE('%Y%m%d', event_date)) AS month,
    CASE
      WHEN geo.region IN ('Nuevo Leon', 'Nuevo León') THEN 'MTY'
      WHEN geo.region = 'Jalisco'                     THEN 'GDL'
      WHEN geo.region IN ('Mexico City', 'Ciudad de Mexico', 'Ciudad de México',
                          'State of Mexico', 'Estado de Mexico', 'Estado de México') THEN 'CDMX'
      ELSE 'Resto'
    END AS plaza,
    user_pseudo_id
  FROM `papyrus-data-mx.analytics_325611813.events_*`
  WHERE _TABLE_SUFFIX >= '20240101'
),
usuarios AS (
  SELECT month, plaza, COUNT(DISTINCT user_pseudo_id) AS users
  FROM ga GROUP BY 1, 2
),
inv AS (
  SELECT
    FORMAT_DATE('%Y-%m', mes) AS month,
    CASE
      WHEN area_metropolitana = 'Zona metropolitana Monterrey'   THEN 'MTY'
      WHEN area_metropolitana = 'Zona metropolitana Guadalajara' THEN 'GDL'
      WHEN area_metropolitana = 'Valle de México'                THEN 'CDMX'
      ELSE 'Resto'
    END AS plaza,
    SUM(spend) AS spend
  FROM `sellers-main-prod.bi_mx.resumen_inversiones_regiones_mexico`
  -- `pais` en esta tabla viene como 'México', NO 'MX'. Con 'MX' el join devuelve spend NULL en
  -- todas las filas y el CPV sale vacío sin ningún error. Verificado con SELECT DISTINCT pais.
  WHERE mes >= '2024-01-01' AND pais = 'México'
  GROUP BY 1, 2
)
SELECT u.month, u.plaza, u.users, i.spend
FROM usuarios u LEFT JOIN inv i USING (month, plaza)
ORDER BY u.month, u.plaza
```

- [ ] **Step 2: Write the failing test**

```python
# marca-mx/tests/test_trafico.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_bq

def test_cpv_es_spend_sobre_usuarios():
    s = sources_bq.traffic_series([
        {"month": "2026-07", "plaza": "MTY", "users": "10000", "spend": "343635.0"}])
    assert s[0]["users"] == 10000
    assert round(s[0]["cpv"], 4) == 34.3635

def test_sin_inversion_el_cpv_es_none_no_cero():
    s = sources_bq.traffic_series([
        {"month": "2026-07", "plaza": "Resto", "users": "500", "spend": None}])
    assert s[0]["spend"] is None
    assert s[0]["cpv"] is None       # un CPV de 0 mentiría: no hubo medición, no hubo gasto cero

def test_usuarios_en_cero_no_divide_por_cero():
    s = sources_bq.traffic_series([
        {"month": "2026-07", "plaza": "GDL", "users": "0", "spend": "100.0"}])
    assert s[0]["cpv"] is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd marca-mx && python3 -m pytest tests/test_trafico.py -v`
Expected: FAIL con `AttributeError: module 'sources_bq' has no attribute 'traffic_series'`

- [ ] **Step 4: Write minimal implementation**

```python
# agregar a marca-mx/sources_bq.py
def traffic_series(rows):
    """Usuarios activos e inversión por (mes, plaza) → CPV. Sin inversión o sin usuarios,
    cpv=None: un cero se leería como 'costó cero', que es distinto de 'no hay dato'."""
    out = []
    for r in rows:
        users = int(r["users"] or 0)
        spend = float(r["spend"]) if r.get("spend") is not None else None
        out.append({
            "month": r["month"], "plaza": r["plaza"], "users": users, "spend": spend,
            "cpv": (spend / users) if (spend is not None and users) else None,
        })
    return sorted(out, key=lambda x: (x["month"], x["plaza"]))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd marca-mx && python3 -m pytest tests/test_trafico.py -v`
Expected: 3 passed

- [ ] **Step 6: Verificación contra datos reales y control de costo**

```bash
cd marca-mx && bq query --use_legacy_sql=false --dry_run --format=json < queries/trafico_plazas.sql
```

Expected: imprime los bytes que escanearía. El export de GA4 es grande; si supera los 20 GB del
`maximum_bytes_billed` del `meta.json`, acotar `_TABLE_SUFFIX` o subir el tope deliberadamente.

```bash
cd marca-mx && python3 -c "
import sources_bq
s = sources_bq.traffic_series(sources_bq.run_query('queries/trafico_plazas.sql'))
for f in s[-12:]: print(f)
print('meses sin inversión:', sorted({f['month'] for f in s if f['spend'] is None})[-6:])
"
```

Expected: MTY de los últimos meses debe empatar con el chart de tráfico del informe
`analisis-mty-multimedios` ya validado. **Si todos los `spend` salen None, la query se pegó a las
tablas muertas de `papyrus-data-mx` en vez de `sellers-main-prod.bi_mx`.**

- [ ] **Step 7: Commit**

```bash
git add marca-mx/queries/trafico_plazas.sql marca-mx/sources_bq.py marca-mx/tests/test_trafico.py
git commit -m "feat(marca): trafico GA4 y CPV por plaza con inversion de bi_mx"
```

---

### Task 4: Driver de Brand Lift (CO+MX) incremental y con techo de llamadas

**Files:**
- Create: `marca-mx/sources_brand_lift.py`
- Create: `marca-mx/brand_lift_cache.json` (semilla; se llena con el backfill supervisado)
- Test: `marca-mx/tests/test_brand_lift.py`

**Interfaces:**
- Produces: `sources_brand_lift.py::parse_results(studies: list, country: str) -> list[dict]`,
  `::needs_refresh(study: dict, cache_rows: list, today: str) -> bool`,
  `::fetch(country: str, max_calls: int = 2) -> list[dict]`,
  `::series(rows: list[dict]) -> list[dict]` (agrupada por mes y pregunta),
  `::ACCOUNTS: dict[str, str]`

**Contexto crítico:** ver la sección "Reglas de trato con la cuenta publicitaria" del spec. Las
llamadas son contra producción. La sonda del 2026-07-27 confirmó la ruta:
`GET /{acct}/ad_studies?fields=...,objectives{id,type,results}` → `results` es una **lista de
strings**, cada uno un JSON con `scoreMean.test` / `scoreMean.control` / `scoreMean.incremental`.

- [ ] **Step 1: Write the failing test**

```python
# marca-mx/tests/test_brand_lift.py
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_brand_lift as BL

RESULT = json.dumps({
    "cell_id": "987465497325149", "experiment_id": "1380313597249074",
    "scoreMean.test": 0.28415, "scoreMean.control": 0.33241,
    "scoreMean.incremental": -0.04826, "brandLiftCILower": -0.08962,
    "brandLiftCIUpper": -0.00212, "responders.test": 689, "responders.control": 676,
    "breakthroughs.singleCellBayesianConfidence": 0.05, "spend": 140867.87,
    "scoreMeanRegion": 0.01017, "scoreMeanVertical": None,
})
STUDY = {"id": "2539254759864543", "name": "HABI MX - Continuous Brand Lift (Jul 2026-Jul 2026)",
         "type": "LIFT", "start_time": "2026-07-01T07:00:00+0000",
         "end_time": "2026-08-01T06:59:59+0000",
         "objectives": {"data": [{"id": "1376237287787800", "type": "BRAND",
                                  "results": [RESULT]}]}}

def test_parse_desenvuelve_el_json_anidado_en_string():
    rows = BL.parse_results([STUDY], "MX")
    assert len(rows) == 1
    r = rows[0]
    assert r["country"] == "MX" and r["month"] == "2026-07"
    assert round(r["exposed"], 5) == 0.28415
    assert round(r["lift"], 5) == -0.04826
    assert r["experiment_id"] == "1380313597249074"

def test_resultado_sin_experiment_id_se_descarta():
    s = dict(STUDY)
    s["objectives"] = {"data": [{"id": "x", "type": "BRAND",
                                 "results": [json.dumps({"cell_id": "1"})]}]}
    assert BL.parse_results([s], "MX") == []

def test_estudio_no_lift_se_ignora():
    s = dict(STUDY, type="SPLIT_TEST_V2")
    assert BL.parse_results([s], "MX") == []

def test_estudio_cerrado_y_ya_cacheado_no_se_reconsulta():
    cache = BL.parse_results([STUDY], "MX")
    assert BL.needs_refresh(STUDY, cache, today="2026-09-15") is False

def test_estudio_cerrado_pero_ausente_del_cache_si_se_consulta():
    assert BL.needs_refresh(STUDY, [], today="2026-09-15") is True

def test_estudio_todavia_abierto_siempre_se_refresca():
    cache = BL.parse_results([STUDY], "MX")
    assert BL.needs_refresh(STUDY, cache, today="2026-07-20") is True

def test_series_agrupa_por_mes_y_pregunta():
    rows = BL.parse_results([STUDY], "MX")
    rows[0]["question"] = "ad_recall"
    s = BL.series(rows)
    assert s[0]["month"] == "2026-07" and s[0]["question"] == "ad_recall"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd marca-mx && python3 -m pytest tests/test_brand_lift.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'sources_brand_lift'`

- [ ] **Step 3: Write minimal implementation**

```python
# marca-mx/sources_brand_lift.py
"""Brand Lift de Meta para CO y MX.

⚠ Estas son cuentas publicitarias de PRODUCCIÓN. La cuota de API es por cuenta y agotarla
throttlea a cualquier otra integración que las consulte. Reglas: techo duro de llamadas por
corrida, nada se re-consulta si ya está cacheado y cerrado, y al primer error transitorio se
aborta conservando el caché. El backfill histórico se corre a mano, nunca desde el cron.
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


def needs_refresh(study, cache_rows, today):
    """Un estudio cerrado y ya cacheado es inmutable: no se vuelve a pedir jamás."""
    cerrado = (study.get("end_time") or "")[:10] < today
    cacheado = any(r["study_id"] == study.get("id") for r in cache_rows)
    return not (cerrado and cacheado)


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


def fetch(country, max_calls=2):
    """Refresco incremental. `max_calls` es un techo duro, no una sugerencia."""
    rows, used = [], 0
    while used < max_calls:
        used += 1
        ok, pl = _get(f"{ACCOUNTS[country]}/ad_studies", fields=FIELDS, limit=10)
        if not ok:
            err = pl.get("error") or {}
            print(f"WARN brand_lift {country}: {err.get('message')} "
                  f"(transient={err.get('is_transient')}) — se conserva el caché")
            break
        rows += parse_results(pl.get("data") or [], country)
        break      # limit=10 cubre el mes en curso y los anteriores: no paginar en el cron
    return rows


def series(rows):
    """Una fila por (país, mes, pregunta). El más reciente gana si hay duplicados."""
    acc = {}
    for r in rows:
        acc[(r["country"], r["month"], r["question"], r["experiment_id"])] = r
    return [acc[k] for k in sorted(acc, key=lambda k: (k[0], k[1], str(k[2])))]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd marca-mx && python3 -m pytest tests/test_brand_lift.py -v`
Expected: 7 passed

- [ ] **Step 5: Sembrar el caché con el backfill ya corrido**

El backfill supervisado (≤4 llamadas MX + ≤3 CO) se corre **fuera de este plan** con
`scratchpad/brand_lift_backfill.py`. Copiar su salida:

```bash
cp /tmp/claude-1000/*/scratchpad/brand_lift_cache.json marca-mx/brand_lift_cache.json
cd marca-mx && python3 -c "
import json; d = json.load(open('brand_lift_cache.json'))
print(d['accounts']); print('filas:', len(d['rows']))
print('meses:', sorted({r['month'] for r in d['rows']})[:3], '…',
      sorted({r['month'] for r in d['rows']})[-3:])
"
```

Expected: MX con ~39 estudios desde 2022-07; CO con su propio conteo. **Cero llamadas nuevas.**

- [ ] **Step 6: Commit**

```bash
git add marca-mx/sources_brand_lift.py marca-mx/brand_lift_cache.json marca-mx/tests/test_brand_lift.py
git commit -m "feat(marca): driver brand lift CO+MX incremental con cache y techo de llamadas"
```

---

### Task 4b: Mapear `experiment_id` → pregunta

**Files:**
- Create: `marca-mx/questions.json`
- Modify: `marca-mx/sources_brand_lift.py` (agregar `map_questions`)
- Test: `marca-mx/tests/test_questions.py`

**Contexto:** cada estudio trae ~4 preguntas y el `experiment_id` **cambia cada mes**, así que no
sirve de llave estable. Los `results` no traen etiqueta. Sin resolver esto, publicar una serie como
"Ad Recall" es adivinar. Las preguntas se identifican por su firma: una tiene ~1000 responders (el
doble de las otras) y lift típicamente negativo; otra vive en 5–10% de tasa base.

- [ ] **Step 1: Identificar cada pregunta con los datos del caché**

```bash
cd marca-mx && python3 -c "
import json
rows = json.load(open('brand_lift_cache.json'))['rows']
for m in sorted({r['month'] for r in rows if r['country']=='MX'})[-9:]:
    print(m)
    for r in sorted([x for x in rows if x['month']==m and x['country']=='MX'],
                    key=lambda x: -(x['exposed'] or 0)):
        print(f\"   exp={r['experiment_id']:<18} exp%={100*(r['exposed'] or 0):6.2f} \"
              f\"ctrl%={100*(r['control'] or 0):6.2f} lift={100*(r['lift'] or 0):+6.2f} \"
              f\"resp_t={r['responders_test']}\")
"
```

Cruzar contra las dos series ya documentadas para nombrar cada firma:
- **TOMA** (del informe MTY): sep-25 14.07/8.33 · oct 15.38/8.21 · nov 18.35/11.34 · dic 19.63/14.09 · ene-26 17.60/11.31 · feb 20.10/14.01 · mar 20.07/11.55
- **Ad Recall** (del informe Uber): máximo expuesto 33.6%, lift máximo +16.3 pts, control hasta 18.1%

- [ ] **Step 2: Write the failing test**

```python
# marca-mx/tests/test_questions.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_brand_lift as BL

def test_asigna_pregunta_por_experiment_id_conocido():
    rows = [{"experiment_id": "1380313597249074", "question": None,
             "responders_test": 689, "exposed": 0.28}]
    out = BL.map_questions(rows, {"1380313597249074": "ad_recall"})
    assert out[0]["question"] == "ad_recall"

def test_experiment_desconocido_queda_marcado_no_inventado():
    rows = [{"experiment_id": "999", "question": None,
             "responders_test": 500, "exposed": 0.07}]
    out = BL.map_questions(rows, {})
    assert out[0]["question"] == "sin_identificar"

def test_sin_identificar_no_entra_a_la_serie_publicable():
    rows = BL.map_questions([{"experiment_id": "999", "question": None,
                              "responders_test": 500, "exposed": 0.07}], {})
    assert BL.publishable(rows) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd marca-mx && python3 -m pytest tests/test_questions.py -v`
Expected: FAIL con `AttributeError: module 'sources_brand_lift' has no attribute 'map_questions'`

- [ ] **Step 4: Write minimal implementation**

```python
# agregar a marca-mx/sources_brand_lift.py
QUESTIONS = os.path.join(HERE, "questions.json")


def load_questions():
    """{experiment_id: nombre_pregunta}. Se llena a mano al identificar cada firma."""
    if not os.path.exists(QUESTIONS):
        return {}
    return json.loads(open(QUESTIONS, encoding="utf-8").read())


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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd marca-mx && python3 -m pytest tests/test_questions.py -v`
Expected: 3 passed

- [ ] **Step 6: Escribir `questions.json` con lo identificado en el Step 1**

```json
{
  "_nota": "experiment_id → pregunta. El id cambia cada mes: hay que agregar los nuevos cada vez que entra un estudio. Identificados por firma y cruce contra las series de TOMA (informe MTY) y Ad Recall (informe Uber).",
  "1380313597249074": "ad_recall"
}
```

- [ ] **Step 7: Commit**

```bash
git add marca-mx/questions.json marca-mx/sources_brand_lift.py marca-mx/tests/test_questions.py
git commit -m "feat(marca): mapeo experiment_id a pregunta, sin adivinar lo no identificado"
```

---

### Task 5: `build.py` — orquestador con aislamiento de fallos

**Files:**
- Modify: `marca-mx/build.py`
- Test: `marca-mx/tests/test_build.py`

**Interfaces:**
- Consumes: `contract.metric/envelope`, `sources_bq.*`, `sources_brand_lift.*`
- Produces: `marca-mx/data.json`; `build.py::collect(now: str) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# marca-mx/tests/test_build.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import build

def test_un_driver_que_falla_no_tumba_a_los_demas(monkeypatch):
    monkeypatch.setattr(build, "collect_exit_poll", lambda: (_ for _ in ()).throw(RuntimeError("bq caído")))
    monkeypatch.setattr(build, "collect_traffic", lambda: [{"month": "2026-07", "plaza": "MTY", "users": 1, "spend": None, "cpv": None}])
    monkeypatch.setattr(build, "collect_brand_lift", lambda c: [])
    d = build.collect(now="2026-07-27T18:00:00Z")
    assert d["metrics"]["exit_poll"]["MX"]["status"] == "error"
    assert "bq caído" in d["metrics"]["exit_poll"]["MX"]["reason"]
    assert d["metrics"]["traffic"]["MX"]["status"] == "ok"

def test_co_declara_not_available_en_trafico_y_exit_poll(monkeypatch):
    monkeypatch.setattr(build, "collect_exit_poll", lambda: [])
    monkeypatch.setattr(build, "collect_traffic", lambda: [])
    monkeypatch.setattr(build, "collect_brand_lift", lambda c: [])
    d = build.collect(now="2026-07-27T18:00:00Z")
    for m in ("traffic", "exit_poll"):
        assert d["metrics"][m]["CO"]["status"] == "not_available"
        assert d["metrics"][m]["CO"]["reason"]
    assert "CO" in d["metrics"]["brand_lift"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd marca-mx && python3 -m pytest tests/test_build.py -v`
Expected: FAIL — `build.collect` no existe

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""Ensambla marca-mx/data.json. Tres drivers independientes: si uno falla, los otros
escriben (mismo criterio de aislamiento que scripts/run_queries.py).
Uso: python3 build.py  (desde la carpeta del tablero; requiere bq autenticado y
META_SYSTEM_USER_TOKEN o META_PCOM_TOKEN para Brand Lift)."""
import datetime
import json
import os

import contract
import sources_bq as BQ
import sources_brand_lift as BL

HERE = os.path.dirname(os.path.abspath(__file__))


def collect_exit_poll():
    return BQ.exit_poll_series(BQ.run_query("queries/exit_poll.sql"))


def collect_traffic():
    return BQ.traffic_series(BQ.run_query("queries/trafico_plazas.sql"))


def collect_brand_lift(country):
    """Caché + refresco incremental. El caché manda: la API solo agrega lo nuevo."""
    cache = [r for r in BL.load_cache() if r["country"] == country]
    fresh = BL.fetch(country)
    # Etiquetar ANTES de deduplicar: series() usa `question` en su llave.
    return BL.publishable(BL.series(BL.map_questions(cache + fresh)))


def _try(fn, *a):
    try:
        return contract.metric("ok", source="bq", series=fn(*a)), None
    except Exception as e:
        print(f"WARN {fn.__name__}: {e}")
        return contract.metric("error", reason=f"{type(e).__name__}: {e}"), e


def collect(now):
    exit_poll_mx, _ = _try(collect_exit_poll)
    traffic_mx, _ = _try(collect_traffic)
    metrics = {
        "brand_lift": {},
        "traffic": {"MX": traffic_mx,
                    "CO": contract.metric("not_available",
                                          reason=contract.NOT_AVAILABLE[("traffic", "CO")])},
        "exit_poll": {"MX": exit_poll_mx,
                      "CO": contract.metric("not_available",
                                            reason=contract.NOT_AVAILABLE[("exit_poll", "CO")])},
    }
    for c in ("MX", "CO"):
        m, err = _try(collect_brand_lift, c)
        if not err:
            m["source"] = "api"
            m["last_updated"] = now
        metrics["brand_lift"][c] = m
    for c in ("MX",):
        for k in ("traffic", "exit_poll"):
            if metrics[k][c]["status"] == "ok":
                metrics[k][c]["last_updated"] = now
    return contract.envelope(metrics, now)


if __name__ == "__main__":
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = collect(now)
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    for k, per in data["metrics"].items():
        for c, m in per.items():
            n = len(m.get("series") or [])
            print(f"  {k:<11} {c}: {m['status']:<14} {n} filas")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd marca-mx && python3 -m pytest tests/ -v`
Expected: todos los tests de las tareas 1-5 pasan

- [ ] **Step 5: Corrida real**

Run: `cd marca-mx && python3 build.py`
Expected: seis líneas de resumen; `brand_lift MX/CO` en `ok`, `traffic/exit_poll MX` en `ok`,
`traffic/exit_poll CO` en `not_available`. **Cero llamadas de más a Meta** (`fetch` usa `limit=10`
y una sola llamada por país).

- [ ] **Step 6: Commit**

```bash
git add marca-mx/build.py marca-mx/tests/test_build.py marca-mx/data.json
git commit -m "feat(marca): build.py orquesta los tres drivers con fallos aislados"
```

---

# FASE 2 — Tablero

### Task 6: Tablero con toggle de país y estados vacíos explícitos

**Files:**
- Create: `marca-mx/index.html`
- Reference: `scripts/templates/dashboard.html` (helper `mkChart`, tema, back-link)

- [ ] **Step 1: Partir de la plantilla**

```bash
cp scripts/templates/dashboard.html marca-mx/index.html
```

Ajustar título, back-link a `../` y el `fetch('data.json')`.

- [ ] **Step 2: Toggle de país y render por estado**

El toggle es el patrón de chips ya aprobado en el repo (single-select). La clave del capítulo es
que **cada métrica se dibuja según su `status`**, no según si su serie viene vacía:

```javascript
// Cada tarjeta de métrica decide qué dibujar por status. Un 'not_available' pinta una
// explicación, NO un chart vacío ni una serie en cero — CO tiene brand lift pero no
// tráfico ni exit poll, y eso tiene que leerse como "falta la fuente".
function renderMetric(el, metric, drawFn) {
  if (!metric || metric.status === 'not_available' || metric.status === 'error') {
    el.innerHTML = `<div class="empty-metric">
        <span class="empty-icon">—</span>
        <p>${metric ? metric.reason : 'Métrica no declarada.'}</p>
      </div>`;
    return;
  }
  if (metric.status === 'stale') {
    el.insertAdjacentHTML('afterbegin',
      `<div class="badge-stale">Dato manual sin actualizar desde ${metric.last_updated}</div>`);
  }
  drawFn(el, metric.series);
}

function render(country) {
  const M = DATA.metrics;
  renderMetric(document.getElementById('brand-lift'), M.brand_lift[country], drawBrandLift);
  renderMetric(document.getElementById('traffic'),    M.traffic[country],    drawTraffic);
  renderMetric(document.getElementById('exit-poll'),  M.exit_poll[country],  drawExitPoll);
}
```

```css
.empty-metric { padding: 32px; text-align: center; color: #94a3b8;
  border: 1px dashed #334155; border-radius: 8px; }
.empty-metric .empty-icon { font-size: 24px; color: #475569; }
.badge-stale { background: #78350f; color: #fde68a; padding: 6px 10px;
  border-radius: 6px; font-size: 12px; margin-bottom: 12px; }
```

- [ ] **Step 3: Los tres charts con Chart.js**

```javascript
const AZUL = '#818cf8', GRIS = '#94a3b8', AMBAR = '#fbbf24', VERDE = '#34d399';
const meses = s => [...new Set(s.map(r => r.month))].sort();

// Brand Lift: expuesto vs control por mes, una pregunta a la vez, más el lift en barras.
function drawBrandLift(el, serie) {
  const q = el.dataset.question || (serie[0] && serie[0].question);
  const s = serie.filter(r => r.question === q);
  const L = meses(s);
  mkChart(el.querySelector('canvas'), {
    type: 'bar',
    data: { labels: L, datasets: [
      { type: 'line', label: 'Expuesto', borderColor: AZUL, yAxisID: 'y',
        data: L.map(m => (s.find(r => r.month === m) || {}).exposed) },
      { type: 'line', label: 'Control', borderColor: GRIS, borderDash: [4, 4], yAxisID: 'y',
        data: L.map(m => (s.find(r => r.month === m) || {}).control) },
      { label: 'Lift (pts)', backgroundColor: AMBAR + '66', yAxisID: 'y1',
        data: L.map(m => (s.find(r => r.month === m) || {}).lift) },
    ]},
    options: { scales: {
      y:  { ticks: { callback: v => (100 * v).toFixed(0) + '%' } },
      y1: { position: 'right', grid: { drawOnChartArea: false },
            ticks: { callback: v => (100 * v).toFixed(0) } } } },
  });
}

// Tráfico y CPV: eje doble. spanGaps:false para que un cpv null deje HUECO, no un cero.
function drawTraffic(el, serie) {
  const plaza = el.dataset.plaza || 'MTY';
  const s = serie.filter(r => r.plaza === plaza), L = meses(s);
  mkChart(el.querySelector('canvas'), {
    type: 'bar',
    data: { labels: L, datasets: [
      { label: 'Usuarios activos', backgroundColor: AZUL + '99', yAxisID: 'y',
        data: L.map(m => (s.find(r => r.month === m) || {}).users) },
      { type: 'line', label: 'CPV', borderColor: AMBAR, yAxisID: 'y1', spanGaps: false,
        data: L.map(m => (s.find(r => r.month === m) || {}).cpv) },
    ]},
    options: { scales: { y1: { position: 'right', grid: { drawOnChartArea: false } } } },
  });
}

// Exit poll: tasa de respuesta y share de Uber sobre las respuestas.
function drawExitPoll(el, serie) {
  const plaza = el.dataset.plaza || 'MTY';
  const s = serie.filter(r => r.plaza === plaza), L = meses(s);
  const uber = r => { const k = Object.keys(r.opciones || {}).find(k => k.toUpperCase().includes('UBER'));
                      return (k && r.respuestas) ? r.opciones[k] / r.respuestas : null; };
  mkChart(el.querySelector('canvas'), {
    type: 'line',
    data: { labels: L, datasets: [
      { label: 'Tasa de respuesta', borderColor: GRIS, yAxisID: 'y',
        data: L.map(m => (s.find(r => r.month === m) || {}).tasa) },
      { label: 'Share Uber', borderColor: VERDE, yAxisID: 'y1', spanGaps: false,
        data: L.map(m => { const r = s.find(x => x.month === m); return r ? uber(r) : null; }) },
    ]},
    options: { scales: {
      y:  { ticks: { callback: v => (100 * v).toFixed(0) + '%' } },
      y1: { position: 'right', grid: { drawOnChartArea: false },
            ticks: { callback: v => (100 * v).toFixed(1) + '%' } } } },
  });
}
```

Los selectores de pregunta y de plaza escriben `el.dataset.question` / `el.dataset.plaza` y
vuelven a llamar `render(country)`. Un solo camino de dibujo, sin estado paralelo.

- [ ] **Step 4: Verificación en localhost**

```bash
cd /home/administrador/habi/tableros-marketing && python3 -m http.server 8091
```

Abrir `http://localhost:8091/marca-mx/`. Comprobar en este orden:
1. Toggle en **MX**: las tres métricas con datos.
2. Toggle en **CO**: Brand Lift con datos; tráfico y exit poll con la explicación, **sin chart
   vacío ni serie en cero**.
3. Un `cpv: null` deja hueco en la línea.
4. La tasa de respuesta del exit poll cae entre 62% y 79%.

- [ ] **Step 5: Commit**

```bash
git add marca-mx/index.html
git commit -m "feat(marca): tablero con toggle CO/MX y estados vacios explicitos"
```

---

### Task 7: Alta en el hub

**Files:**
- Modify: `index.html` (**generado** — vía `scripts/build_hub.py`, no a mano)

- [ ] **Step 1: Regenerar el hub**

```bash
cd /home/administrador/habi/tableros-marketing && python3 scripts/build_hub.py && git diff --stat index.html
```

Expected: `index.html` gana una card en la sección Dashboards.

- [ ] **Step 2: Confirmar que el cron lo recoge**

```bash
python3 -c "
import sys; sys.path.insert(0,'scripts'); import run_queries, pathlib
jobs = run_queries.discover_jobs(pathlib.Path('.'))
print([j['slug'] for j in jobs if j['slug']=='marca-mx'])
print([str(j['build_py']) for j in jobs if j['slug']=='marca-mx'])
"
```

Expected: `['marca-mx']` y su `build.py`. Si sale vacío, `meta.json` no es válido o falta `build.py`.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(hub): alta del tablero de marca"
```

---

# FASE 3 — Generador de informes

### Task 8: Estructura del contenido editorial y merge base + mes

**Files:**
- Create: `informe-uber-ooh/render.py`
- Create: `informe-uber-ooh/contenido/informe.json`
- Create: `informe-uber-ooh/contenido/base/01-resumen-ejecutivo.md` (semilla)
- Test: `informe-uber-ooh/tests/test_merge.py`

**Cómo se mete el editorial (respuesta al requerimiento):** un archivo Markdown por capítulo. El
prefijo numérico del nombre da el orden. `contenido/base/` son los capítulos estables; una carpeta
`contenido/YYYY-MM/` con un archivo del mismo nombre **reemplaza** ese capítulo ese mes, y un
archivo con nombre nuevo **agrega** un capítulo. Para el informe de agosto solo se escribe lo que
cambia.

```
contenido/
├── informe.json                    ← metadata de la campaña (título, plazas, periodo, inversión)
├── base/
│   ├── 01-resumen-ejecutivo.md
│   ├── 02-rigor-operativo.md
│   ├── 03-amplificacion.md
│   ├── 04-brand-lift.md
│   ├── 05-trafico-cpv.md
│   ├── 06-exit-poll.md
│   └── 08-conclusion.md
└── 2026-07/
    └── 07-propuesta-continuidad.md ← solo del mes
```

**Interfaces:**
- Produces: `render.py::chapters_for(month: str, root: str) -> list[dict]` con llaves
  `id, order, title, body`

- [ ] **Step 1: Write the failing test**

```python
# informe-uber-ooh/tests/test_merge.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import render

def _write(tmp, rel, text):
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

def test_orden_por_prefijo_numerico(tmp_path):
    _write(tmp_path, "base/02-rigor.md", "# Rigor\nbase")
    _write(tmp_path, "base/01-resumen.md", "# Resumen\nbase")
    ch = render.chapters_for("2026-07", str(tmp_path))
    assert [c["order"] for c in ch] == [1, 2]
    assert ch[0]["title"] == "Resumen"

def test_archivo_del_mes_reemplaza_al_de_base(tmp_path):
    _write(tmp_path, "base/01-resumen.md", "# Resumen\nviejo")
    _write(tmp_path, "2026-07/01-resumen.md", "# Resumen\nnuevo")
    ch = render.chapters_for("2026-07", str(tmp_path))
    assert len(ch) == 1 and "nuevo" in ch[0]["body"]

def test_archivo_nuevo_del_mes_agrega_capitulo(tmp_path):
    _write(tmp_path, "base/01-resumen.md", "# Resumen\nbase")
    _write(tmp_path, "2026-07/07-propuesta.md", "# Propuesta\nQ3")
    ch = render.chapters_for("2026-07", str(tmp_path))
    assert [c["order"] for c in ch] == [1, 7]

def test_el_mes_de_otro_periodo_no_se_mezcla(tmp_path):
    _write(tmp_path, "base/01-resumen.md", "# Resumen\nbase")
    _write(tmp_path, "2026-06/07-vieja.md", "# Vieja\njunio")
    ch = render.chapters_for("2026-07", str(tmp_path))
    assert len(ch) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd informe-uber-ooh && python3 -m pytest tests/test_merge.py -v`
Expected: FAIL — `render` no existe

- [ ] **Step 3: Write minimal implementation**

```python
# informe-uber-ooh/render.py
"""Renderiza una edición del informe: capítulos en Markdown + datos del tablero de marca.

Un .md por capítulo. El prefijo numérico da el orden; un archivo homónimo en la carpeta del
mes reemplaza el de base, y un nombre nuevo agrega capítulo. Markdown y no YAML porque el
runner del cron solo tiene stdlib, y porque escribir prosa ejecutiva en YAML es un dolor.
"""
import os
import re

CH_RE = re.compile(r"^(\d+)-")


def _read_chapter(path):
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else ""
    body = "\n".join(lines[1:]).strip()
    name = os.path.basename(path)
    return {"id": name[:-3], "order": int(CH_RE.match(name).group(1)),
            "title": title, "body": body}


def chapters_for(month, root):
    """base/ mezclado con root/<month>/. Mismo nombre reemplaza; nombre nuevo agrega."""
    found = {}
    for folder in ("base", month):
        d = os.path.join(root, folder)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".md") and CH_RE.match(name):
                found[name] = _read_chapter(os.path.join(d, name))
    return sorted(found.values(), key=lambda c: c["order"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd informe-uber-ooh && python3 -m pytest tests/test_merge.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add informe-uber-ooh/render.py informe-uber-ooh/tests/test_merge.py informe-uber-ooh/contenido/
git commit -m "feat(informe): capitulos en markdown con merge base mas mes"
```

---

### Task 9: Interpolación de datos en el texto, con fallo ruidoso

**Files:**
- Modify: `informe-uber-ooh/render.py` (agregar `interpolate`, `resolve`)
- Test: `informe-uber-ooh/tests/test_interpolate.py`

**Cómo se conecta el editorial con los datos:** el texto lleva `{{ruta.al.dato}}` y el render lo
sustituye desde el `data.json` del tablero. Así una cifra del informe **no puede** divergir del
tablero: no hay número escrito a mano.

La ruta tiene **exactamente cuatro partes**: `<metrica>.<pais>.<campo>.<selector>`.

```markdown
El share de atribución declarada a Uber alcanzó {{exit_poll.MX.uber_share.latest:pct2}}
en {{exit_poll.MX.uber_share.latest:month}}, sobre una tasa de respuesta de
{{exit_poll.MX.tasa.latest:pct1}}.
```

- [ ] **Step 1: Write the failing test**

```python
# informe-uber-ooh/tests/test_interpolate.py
import sys, pathlib, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import render

DATA = {"metrics": {"exit_poll": {"MX": {"status": "ok", "series": [
    {"month": "2026-06", "plaza": "MTY", "registros_web": 100, "respuestas": 80,
     "tasa": 0.8, "opciones": {"Publicidad en branding de coches de UBER": 4}},
    {"month": "2026-07", "plaza": "MTY", "registros_web": 100, "respuestas": 50,
     "tasa": 0.5, "opciones": {"Publicidad en branding de coches de UBER": 5}},
]}}}}

def test_interpola_valor_con_formato_de_porcentaje():
    out = render.interpolate("tasa {{exit_poll.MX.tasa.latest:pct1}}", DATA)
    assert out == "tasa 50.0%"

def test_interpola_el_mes_del_ultimo_dato():
    out = render.interpolate("corte {{exit_poll.MX.tasa.latest:month}}", DATA)
    assert out == "corte 2026-07"

def test_placeholder_que_no_resuelve_aborta_el_render():
    with pytest.raises(render.UnresolvedPlaceholder) as e:
        render.interpolate("{{exit_poll.MX.inventado.latest:pct1}}", DATA)
    assert "exit_poll.MX.inventado.latest" in str(e.value)

def test_metrica_not_available_aborta_en_vez_de_poner_cero():
    data = {"metrics": {"traffic": {"CO": {"status": "not_available", "reason": "sin GA4"}}}}
    with pytest.raises(render.UnresolvedPlaceholder):
        render.interpolate("{{traffic.CO.users.latest:num}}", data)

def test_texto_sin_placeholders_pasa_intacto():
    assert render.interpolate("sin nada", DATA) == "sin nada"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd informe-uber-ooh && python3 -m pytest tests/test_interpolate.py -v`
Expected: FAIL — `render.interpolate` no existe

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a informe-uber-ooh/render.py
PH_RE = re.compile(r"\{\{([a-zA-Z0-9_.]+)(?::([a-z0-9]+))?\}\}")

def _uber(f):
    return next((v for k, v in (f.get("opciones") or {}).items() if "UBER" in k.upper()), None)


FIELDS = {"tasa": lambda f: f.get("tasa"),
          "users": lambda f: f.get("users"),
          "cpv": lambda f: f.get("cpv"),
          "uber": _uber,
          "uber_share": lambda f: (_uber(f) / f["respuestas"]
                                   if _uber(f) is not None and f.get("respuestas") else None)}


class UnresolvedPlaceholder(Exception):
    """Un placeholder sin resolver aborta el render. Nunca se emite '{{...}}' literal ni un
    cero silencioso en un documento que se manda a comité."""


def _fmt(value, spec):
    if spec in (None, "raw"):
        return str(value)
    if spec == "num":
        return f"{value:,.0f}".replace(",", ".")
    if spec == "pct1":
        return f"{100*value:.1f}%"
    if spec == "pct2":
        return f"{100*value:.2f}%"
    if spec == "pts":
        return f"{100*value:+.1f} pts"
    raise UnresolvedPlaceholder(f"formato desconocido: {spec}")


def resolve(path, data):
    """`<metrica>.<pais>.<campo>.<selector>`. Selector soportado: `latest`."""
    parts = path.split(".")
    if len(parts) != 4:
        raise UnresolvedPlaceholder(f"{path}: se esperaba metrica.pais.campo.selector")
    metric, country, field, selector = parts
    m = ((data.get("metrics") or {}).get(metric) or {}).get(country)
    if not m or m.get("status") != "ok":
        raise UnresolvedPlaceholder(
            f"{path}: la métrica está en '{(m or {}).get('status')}', no hay dato que citar")
    serie = m.get("series") or []
    if not serie:
        raise UnresolvedPlaceholder(f"{path}: serie vacía")
    row = sorted(serie, key=lambda r: r["month"])[-1] if selector == "latest" else None
    if row is None:
        raise UnresolvedPlaceholder(f"{path}: selector '{selector}' no soportado")
    if field == "month":
        return row["month"], "raw"
    getter = FIELDS.get(field)
    if not getter:
        raise UnresolvedPlaceholder(f"{path}: campo '{field}' desconocido")
    value = getter(row)
    if value is None:
        raise UnresolvedPlaceholder(f"{path}: el campo existe pero vale None")
    return value, None


def interpolate(text, data):
    """`:month` devuelve el mes del dato citado, para que texto y cifra no se desincronicen."""
    def sub(m):
        path, spec = m.group(1), m.group(2)
        if spec == "month":
            p = path.split(".")
            if len(p) != 4:
                raise UnresolvedPlaceholder(f"{path}: se esperaba metrica.pais.campo.selector")
            path, spec = f"{p[0]}.{p[1]}.month.{p[3]}", None
        value, forced = resolve(path, data)
        return _fmt(value, forced or spec)
    return PH_RE.sub(sub, text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd informe-uber-ooh && python3 -m pytest tests/test_interpolate.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add informe-uber-ooh/render.py informe-uber-ooh/tests/test_interpolate.py
git commit -m "feat(informe): interpolacion de datos con fallo ruidoso"
```

---

### Task 10: Bloques de gráfica y tabla dentro de los capítulos

**Files:**
- Modify: `informe-uber-ooh/render.py` (agregar `parse_blocks`, `md_to_html`)
- Test: `informe-uber-ooh/tests/test_blocks.py`

**Cómo se piden gráficas desde el editorial:** una valla ```chart con `clave: valor`. Sin YAML.

````markdown
Como se observa en la serie histórica:

```chart
tipo: linea
metrica: brand_lift
pais: MX
pregunta: ad_recall
caption: Gráfica 2 — consolidado histórico de Brand Lift
```
````

- [ ] **Step 1: Write the failing test**

```python
# informe-uber-ooh/tests/test_blocks.py
import sys, pathlib, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import render

MD = """Texto antes.

```chart
tipo: linea
metrica: brand_lift
pais: MX
caption: Gráfica 2 — histórico
```

Texto después.
"""

def test_extrae_el_bloque_y_deja_marcador_en_el_texto():
    body, blocks = render.parse_blocks(MD)
    assert len(blocks) == 1
    assert blocks[0]["tipo"] == "linea" and blocks[0]["metrica"] == "brand_lift"
    assert blocks[0]["caption"] == "Gráfica 2 — histórico"
    assert "@@BLOCK0@@" in body and "```" not in body

def test_bloque_sin_metrica_es_error_de_autoria():
    with pytest.raises(render.BadBlock):
        render.parse_blocks("```chart\ntipo: linea\n```")

def test_bloque_que_apunta_a_metrica_inexistente_es_error():
    with pytest.raises(render.BadBlock):
        render.parse_blocks("```chart\ntipo: linea\nmetrica: inventada\npais: MX\n```")

def test_markdown_basico_a_html():
    html = render.md_to_html("## Sub\n\n- uno\n- dos\n\nPárrafo con **negrita**.")
    assert "<h2>Sub</h2>" in html and "<li>uno</li>" in html and "<strong>negrita</strong>" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd informe-uber-ooh && python3 -m pytest tests/test_blocks.py -v`
Expected: FAIL — `render.parse_blocks` no existe

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a informe-uber-ooh/render.py
from html import escape

BLOCK_RE = re.compile(r"^```chart\s*$(.*?)^```\s*$", re.MULTILINE | re.DOTALL)
METRICS_OK = ("brand_lift", "traffic", "exit_poll")


class BadBlock(Exception):
    """Bloque mal escrito: es un error de autoría, se falla en el render y no se publica."""


def parse_blocks(md):
    """Saca los bloques ```chart y los reemplaza por @@BLOCKn@@."""
    blocks = []

    def take(m):
        spec = {}
        for line in m.group(1).strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                spec[k.strip()] = v.strip()
        if spec.get("metrica") not in METRICS_OK:
            raise BadBlock(f"bloque sin `metrica` válida (opciones: {METRICS_OK}): {spec}")
        if not spec.get("pais"):
            raise BadBlock(f"bloque sin `pais`: {spec}")
        blocks.append(spec)
        return f"@@BLOCK{len(blocks)-1}@@"

    return BLOCK_RE.sub(take, md), blocks


def md_to_html(md):
    """Markdown mínimo: encabezados, listas, negrita, cursiva, links, párrafos.
    Suficiente para prosa ejecutiva y sin dependencias."""
    out, in_list = [], False
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(s[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if not s:
            continue
        if s.startswith("### "):
            out.append(f"<h3>{_inline(s[4:])}</h3>")
        elif s.startswith("## "):
            out.append(f"<h2>{_inline(s[3:])}</h2>")
        elif s.startswith("@@BLOCK"):
            out.append(s)
        else:
            out.append(f"<p>{_inline(s)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _inline(t):
    t = escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", t)
    return re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', t)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd informe-uber-ooh && python3 -m pytest tests/test_blocks.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add informe-uber-ooh/render.py informe-uber-ooh/tests/test_blocks.py
git commit -m "feat(informe): bloques chart y markdown a html sin dependencias"
```

---

### Task 11: `build.py` del informe — congelado del mes e índice de ediciones

**Files:**
- Create: `informe-uber-ooh/build.py`
- Create: `informe-uber-ooh/meta.json`
- Create: `informe-uber-ooh/plantilla.html`
- Test: `informe-uber-ooh/tests/test_freeze.py`

**Interfaces:**
- Consumes: `render.chapters_for`, `render.interpolate`, `render.parse_blocks`, `render.md_to_html`
- Produces: `informe-uber-ooh/<YYYY-MM>/index.html`, `informe-uber-ooh/index.html`

- [ ] **Step 1: Write the failing test**

```python
# informe-uber-ooh/tests/test_freeze.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import build

def test_solo_escribe_el_mes_pedido(tmp_path):
    (tmp_path / "2026-06").mkdir()
    viejo = tmp_path / "2026-06" / "index.html"
    viejo.write_text("EDICION DE JUNIO", encoding="utf-8")
    build.write_edition("2026-07", root=str(tmp_path), html="<p>julio</p>")
    assert viejo.read_text(encoding="utf-8") == "EDICION DE JUNIO"   # inmutable
    assert (tmp_path / "2026-07" / "index.html").exists()

def test_indice_lista_las_ediciones_de_mas_nueva_a_mas_vieja(tmp_path):
    for m in ("2026-06", "2026-07", "2026-05"):
        (tmp_path / m).mkdir()
        (tmp_path / m / "index.html").write_text("x", encoding="utf-8")
    assert build.editions(str(tmp_path)) == ["2026-07", "2026-06", "2026-05"]

def test_el_indice_ignora_carpetas_que_no_son_meses(tmp_path):
    for d in ("assets", "contenido", "tests", "2026-07"):
        (tmp_path / d).mkdir()
    (tmp_path / "2026-07" / "index.html").write_text("x", encoding="utf-8")
    assert build.editions(str(tmp_path)) == ["2026-07"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd informe-uber-ooh && python3 -m pytest tests/test_freeze.py -v`
Expected: FAIL — `build` no existe

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""Renderiza la edición del mes en curso del informe de campaña.

Solo escribe la carpeta del mes actual: al cambiar de mes, la anterior deja de tocarse y
queda inmutable por construcción, sin un paso manual que alguien pueda olvidar.
`--freeze YYYY-MM` sella un mes concreto antes de tiempo.
Los datos se hornean desde marca-mx/data.json: una edición pasada no depende de nada externo.
"""
import argparse
import datetime
import json
import os
import re

import render

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "marca-mx", "data.json")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def editions(root=HERE):
    return sorted([d for d in os.listdir(root)
                   if MONTH_RE.match(d) and os.path.exists(os.path.join(root, d, "index.html"))],
                  reverse=True)


def write_edition(month, root=HERE, html=""):
    d = os.path.join(root, month)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return os.path.join(d, "index.html")


def build_html(month, data, plantilla):
    """Capítulos → interpolación → bloques → HTML. Un placeholder sin resolver aborta."""
    partes, charts = [], []
    for ch in render.chapters_for(month, os.path.join(HERE, "contenido")):
        body = render.interpolate(ch["body"], data)
        body, blocks = render.parse_blocks(body)
        html = render.md_to_html(body)
        for i, b in enumerate(blocks):
            idx = len(charts)
            charts.append(b)
            html = html.replace(f"@@BLOCK{i}@@",
                                f'<figure class="chart"><canvas id="c{idx}"></canvas>'
                                f'<figcaption>{b.get("caption","")}</figcaption></figure>')
        partes.append(f'<section id="{ch["id"]}"><h1>{ch["title"]}</h1>{html}</section>')
    # Los slots de la plantilla usan comentarios HTML, NO {{...}}: así no se confunden
    # con los placeholders de datos del editorial, que son otra capa y ya se resolvieron.
    return (plantilla
            .replace("<!--MONTH-->", month)
            .replace("<!--CHAPTERS-->", "\n".join(partes))
            .replace("<!--CHARTS-->", json.dumps(charts, ensure_ascii=False))
            .replace("<!--DATA-->", json.dumps(data, ensure_ascii=False)))


def build_index(root=HERE):
    items = "\n".join(f'<li><a href="{m}/">{m}</a></li>' for m in editions(root))
    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as f:
        f.write(f"<h1>Informe de impacto — Uber OOH</h1><ul>{items}</ul>")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", help="sellar un mes concreto (YYYY-MM)")
    args = ap.parse_args()
    month = args.freeze or datetime.date.today().strftime("%Y-%m")
    data = json.loads(open(DATA, encoding="utf-8").read())
    plantilla = open(os.path.join(HERE, "plantilla.html"), encoding="utf-8").read()
    print("escrito:", write_edition(month, html=build_html(month, data, plantilla)))
    build_index()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd informe-uber-ooh && python3 -m pytest tests/ -v`
Expected: todos pasan

- [ ] **Step 5: Crear `plantilla.html` y `meta.json`**

```html
<!-- informe-uber-ooh/plantilla.html -->
<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Informe de impacto — Uber OOH · <!--MONTH--></title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🚗</text></svg>">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  body { background:#0f172a; color:#e2e8f0; font:16px/1.7 system-ui,sans-serif;
         max-width:820px; margin:0 auto; padding:0 24px 80px; }
  h1 { color:#f8fafc; font-size:24px; margin:48px 0 16px; }
  h2 { color:#f8fafc; font-size:19px; margin:32px 0 12px; }
  section { border-top:1px solid #334155; }
  .chart { background:#1e293b; border:1px solid #334155; border-radius:8px;
           padding:16px; margin:24px 0; }
  figcaption { color:#94a3b8; font-size:13px; text-align:center; margin-top:8px; }
  #bar { position:fixed; top:0; left:0; height:3px; background:#818cf8; width:0; z-index:9; }
  .edicion { color:#94a3b8; font-size:13px; padding-top:24px; }
</style></head><body>
<div id="bar"></div>
<p class="edicion">Edición <!--MONTH--> · datos congelados al cierre de mes ·
   <a href="../">ver otras ediciones</a></p>
<!--CHAPTERS-->
<script>
const DATA = <!--DATA-->, CHARTS = <!--CHARTS-->;
addEventListener('scroll', () => {
  const h = document.body.scrollHeight - innerHeight;
  document.getElementById('bar').style.width = (100 * scrollY / h) + '%';
});
// Cada bloque ```chart del editorial se convirtió en un canvas c0, c1, … en orden.
CHARTS.forEach((spec, i) => {
  const m = DATA.metrics[spec.metrica][spec.pais];
  const cv = document.getElementById('c' + i);
  if (!m || m.status !== 'ok') {
    cv.replaceWith(Object.assign(document.createElement('p'),
      { textContent: m ? m.reason : 'Métrica no declarada.', style: 'color:#94a3b8' }));
    return;
  }
  DRAW[spec.metrica](cv, m.series, spec);
});
</script></body></html>
```

`DRAW` es el mismo trío de funciones del tablero (`drawBrandLift` / `drawTraffic` /
`drawExitPoll`), copiadas a la plantilla. Se duplican a propósito: una edición congelada no puede
depender de un archivo del tablero que mañana cambie, o dejaría de ser inmutable.

`meta.json`:

```json
{
  "title": "Informe de impacto — Uber OOH (MX)",
  "description": "Evaluación mensual de la campaña de branding en vehículos de Uber: Brand Lift, tráfico, CPV y atribución declarada.",
  "country": "MX",
  "section": "analysis",
  "order": 8
}
```

- [ ] **Step 6: Verificar la inmutabilidad de verdad**

```bash
cd informe-uber-ooh && python3 build.py --freeze 2026-07 && git add -A && git commit -m "wip: edicion julio"
python3 build.py --freeze 2026-08 && git status --short 2026-07/
```

Expected: `git status` de `2026-07/` **vacío**. Si aparece modificado, `write_edition` está tocando
meses que no le corresponden.

- [ ] **Step 7: Commit**

```bash
git add informe-uber-ooh/
git commit -m "feat(informe): render de edicion mensual congelada e indice"
```

---

### Task 12: Contenido editorial del informe de Uber

**Files:**
- Create: los 8 `.md` de `informe-uber-ooh/contenido/base/` y `contenido/2026-07/`
- Create: `informe-uber-ooh/assets/` (mapas de zonas MTY y GDL)

**Fuente:** el Google Doc original (`1n0dPiLApnCck9Rsc5BVplXzN0n-pKZvFwqbhqB1_0xI`). Tono: audiencia
ejecutiva, sin jerga; cuando la campaña muestre señal real pero modesta frente a la inversión, se
argumenta el impacto y se explicita el ROI bajo.

- [ ] **Step 1: Capítulos 1-3 y 7-8 (editorial, del doc original)**

Trasladar el texto tal cual, sustituyendo **toda** cifra por su placeholder. Regla: si un número
del texto también vive en el tablero, va como `{{...}}`; si no, es un dato editorial (inversión
contratada, unidades de flota, precios de Bullmedia) y va literal.

- [ ] **Step 2: Capítulos 4-6 (datos) con sus bloques**

Cada uno lleva su análisis interpretativo más el bloque ```chart correspondiente.

- [ ] **Step 3: Corregir la afirmación del 2% (decisión del spec)**

El doc original dice que la atribución declarada a Uber "alcanza un 2% en marzo de 2026". La serie
recalculada da 1.62% en MTY+GDL y 0.63% nacional en marzo; el 2% se alcanza en mayo. El capítulo 6
publica la serie recalculada con nota al pie de que la cifra previa correspondía a otro corte.

- [ ] **Step 4: Verificar que no quedó ningún placeholder sin resolver**

```bash
cd informe-uber-ooh && python3 build.py --freeze 2026-07 && grep -c "{{" 2026-07/index.html
```

Expected: `0`. Si `build.py` lanza `UnresolvedPlaceholder`, el mensaje dice exactamente qué ruta
falló — corregir el `.md`, no el render.

- [ ] **Step 5: Revisión en localhost y push final**

```bash
python3 scripts/build_hub.py && python3 -m http.server 8091
```

Revisar `/marca-mx/` y `/informe-uber-ooh/2026-07/` desde el worktree.

```bash
git add -A && git commit -m "feat(informe): contenido editorial del informe Uber OOH"
```

**Commit a la rama, nada de push.** El trabajo vive en `feat/tablero-marca-informes`; la
integración a `main` la decide Camilo al final, con
superpowers:finishing-a-development-branch. Ningún implementador debe pushear ni tocar `main`:
`main` es lo que sirve GitHub Pages y el cron le escribe cada 4 horas.

---

## Verificación de extremo a extremo

1. `cd marca-mx && python3 -m pytest tests/ -v && cd ../informe-uber-ooh && python3 -m pytest tests/ -v` — todo verde.
2. `cd marca-mx && python3 build.py` — seis líneas de estado; CO en `not_available` para tráfico y exit poll.
3. Tasa de respuesta del exit poll entre 62% y 79% (si sale ~20%, se perdió `fuente_id = 3`).
4. Tráfico de MTY empata con el chart ya validado de `analisis-mty-multimedios`.
5. CPV de CDMX no inflado por el desajuste `Valle de México` ↔ GA4.
6. Toggle en CO: Brand Lift con datos, las otras dos con explicación y sin chart vacío.
7. Congelar julio, generar agosto, `git status 2026-07/` vacío.
8. `grep -c "{{" 2026-07/index.html` → 0.
9. **IAM**: correr `update-data.yml` con `workflow_dispatch` y confirmar que la query de CPV lee
   `sellers-main-prod.bi_mx` desde el runner. Que funcione en local no lo garantiza.
10. Confirmar que el System User tiene "Ver rendimiento" y **no** "Administrar campañas" sobre
    `act_205661715114408`.
