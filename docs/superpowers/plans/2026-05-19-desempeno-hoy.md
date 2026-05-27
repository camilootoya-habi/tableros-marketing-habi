# Desempeño hoy — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el sub-tablero `desempeno-hoy/` que muestra calificados MM (estados 20/63, primer entrance) del día actual hora-por-hora, con selectores de país (CO/MX) y multi-select de fuentes, comparados contra mismo día sem. pasada y promedio de los últimos 4 mismos-días-de-semana. Auto-refresh cada 15 min vía GitHub Actions + botón "recargar" manual.

**Architecture:** Workflow GitHub Actions separado (`desempeno-hoy.yml`, cron `*/15 * * * *` UTC) corre 2 queries BQ (CO + MX), las transforma a JSON con Python, commitea `data.json`. Frontend estático con HTML + vanilla JS + Chart.js (CDN). Sin backend.

**Tech Stack:** BigQuery, Python 3 (transformer), HTML + vanilla JS + Chart.js (CDN), GitHub Actions, GitHub Pages.

**Spec de referencia:** `docs/superpowers/specs/2026-05-19-desempeno-hoy-design.md`

---

## Notas previas para el ejecutor

- **No hay framework de tests** en este repo. Validación es:
  - SQL: correr contra BQ real con `bq query` y verificar volúmenes/estructura contra spot-checks conocidos.
  - Python: ejecutar con la salida real de BQ y validar shape del JSON.
  - Frontend: abrir `index.html` localmente (`python3 -m http.server 8000`) y validar interacciones; luego validar en GitHub Pages tras deploy.
- **Working directory:** `~/habi/tableros-marketing/`.
- **Convenciones del repo** (ver `general.md` de memoria):
  - Favicon megáfono SVG inline (ver Task 6).
  - Back link al inicio del `<body>`.
  - Dark theme: bg `#0f172a`, cards `#1e293b`, borders `#334155`, acento `#818cf8`, texto `#f8fafc` / `#e2e8f0` / `#94a3b8`.
  - `<style>` inline en `index.html`, no CSS compartido.
  - Sin emojis en código (excepto favicon).
- **Spot-checks de calificación para validar SQL CO:**
  - Estados 20 ("calificado") y 63 ("sin pricing incial") en `habi_db_tabla_estados` — confirmar.
  - Volumen esperado CO últimos 7 días: del orden de cientos-bajos miles por día de calificados (verificable contra WBR).
- **Frequent commits** — cada task termina con su propio commit.

---

## Task 1: Scaffold de la carpeta + README

**Files:**
- Create: `desempeno-hoy/index.html` (vacío por ahora)
- Create: `desempeno-hoy/query.sql` (vacío por ahora)
- Create: `desempeno-hoy/README.md`

- [ ] **Step 1: Crear la carpeta**

```bash
cd ~/habi/tableros-marketing
mkdir -p desempeno-hoy
```

- [ ] **Step 2: Crear archivos placeholder**

```bash
touch desempeno-hoy/index.html desempeno-hoy/query.sql
```

- [ ] **Step 3: Crear `desempeno-hoy/README.md`**

```markdown
# desempeno-hoy/

Tablero live de calificados MM del día actual (estados 20/63, primer entrance),
hora por hora, con selector de país (CO/MX) y multi-select de fuentes.

Comparativos: hoy vs hace 7 días vs promedio últimos 4 mismos días de semana.

Spec: `docs/superpowers/specs/2026-05-19-desempeno-hoy-design.md`
Live: https://camilootoya-habi.github.io/tableros-marketing-habi/desempeno-hoy/

Auto-update: workflow `.github/workflows/desempeno-hoy.yml` cada 15 min UTC.
```

- [ ] **Step 4: Commit**

```bash
git add desempeno-hoy/
git commit -m "Scaffold desempeno-hoy/ (carpeta + README + placeholders)"
```

---

## Task 2: Smoke test del SQL CO — validar joins, TZ y volumen

**Files:**
- (No crea ni modifica; es exploración manual contra BQ.)

**Goal:** validar 3 cosas antes de escribir el SQL final:
1. Que `state_id IN (20, 63)` en `habi_db_tabla_historico_estado_v2` se llama `estado_id` o `state_id` (los tableros del repo usan ambas variantes).
2. Que el JOIN `nid ↔ id_negocio` funciona limpio.
3. Que el orden de magnitud diario sea sensato (cientos-miles).

- [ ] **Step 1: Inspeccionar columnas de la tabla histórico CO**

```bash
bq show --schema --format=prettyjson sellers-main-prod:co_rds_staging.habi_db_tabla_historico_estado_v2 | head -50
```

Anotar: nombre de columna del estado (`estado_id` o `state_id`) y nombre del id de negocio (`negocio_id`, `id_negocio` o similar). Usar el nombre real en los siguientes pasos.

- [ ] **Step 2: Validar volumen últimos 7 días — calificados CO**

```bash
bq query --use_legacy_sql=false --format=pretty "
WITH primer_calif AS (
  SELECT negocio_id, MIN(fecha_creacion) AS ts_calif_utc
  FROM \`sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2\`
  WHERE estado_id IN (20, 63)
    AND fecha_creacion >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  GROUP BY 1
)
SELECT DATE(TIMESTAMP_ADD(ts_calif_utc, INTERVAL -5 HOUR)) AS fecha_co,
       COUNT(DISTINCT negocio_id) AS calificados
FROM primer_calif
GROUP BY 1 ORDER BY 1
"
```

Expected: 7 filas, con volúmenes de orden de magnitud cientos-bajos miles/día. Si falla por nombre de columna, ajustar al schema real.

- [ ] **Step 3: Validar join con TIG-CO**

```bash
bq query --use_legacy_sql=false --format=pretty "
WITH primer_calif AS (
  SELECT negocio_id, MIN(fecha_creacion) AS ts_calif_utc
  FROM \`sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2\`
  WHERE estado_id IN (20, 63)
    AND fecha_creacion >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  GROUP BY 1
),
lead_fuente AS (
  SELECT nid, fuente_id FROM \`papyrus-data.habi_wh_bi.tabla_inmuebles_general\`
  WHERE fecha_creacion >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
    AND nid IS NOT NULL
    AND fuente_id IN (3,7,20,35,37,39,41,42,47)
)
SELECT f.fuente_id, COUNT(DISTINCT p.negocio_id) AS calificados
FROM primer_calif p
JOIN lead_fuente f ON f.nid = p.negocio_id  -- nid ↔ negocio_id ¿match?
GROUP BY 1 ORDER BY 2 DESC
"
```

Expected: 6 filas (una por cada fuente_id ∈ {3,7,20,35,39,47}; Leadforms se ramifica en 47/37/41/42). Si el join devuelve 0 filas en todas las fuentes, el campo de join NO es `nid ↔ negocio_id` y hay que investigar (probablemente `nid` esté en TIG como string vs int, o el id correcto sea otro).

- [ ] **Step 4: Validar volumen MX y schema MX**

```bash
bq show --schema --format=prettyjson sellers-main-prod:mx_rds_staging.habi_db_history_state | head -30
```

Anotar: en MX la columna se llama `state_id` y el id es `deal_id`. Verificar y anotar el path para llegar al nid de TIG-MX (puede ser `deal_id → property_deal.id → nid` o `deal_id` ya sea nid). Si hace falta JOIN intermedio con `habi_db_property_deal`, anotarlo para Task 3.

```bash
bq query --use_legacy_sql=false --format=pretty "
SELECT DATE(TIMESTAMP_ADD(MIN(fecha_creacion), INTERVAL -6 HOUR)) AS fecha_mx,
       COUNT(DISTINCT deal_id) AS calificados_aprox
FROM \`sellers-main-prod.mx_rds_staging.habi_db_history_state\`
WHERE state_id IN (20, 63)
  AND fecha_creacion >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY 1 ORDER BY 1
"
```

Si la columna de fecha en MX no se llama `fecha_creacion` (puede ser `date_create`), ajustar. La memoria `tablas_core.md` dice MX usa inglés.

- [ ] **Step 5: Anotar findings en `desempeno-hoy/NOTAS_SMOKE.md`**

Crear archivo con los hallazgos exactos: nombre de columnas reales, JOIN correcto, volúmenes encontrados. Este archivo se borra antes del commit final, pero sirve como referencia para Task 3.

- [ ] **Step 6: Commit (solo si NOTAS_SMOKE.md tiene info; opcional)**

```bash
# Opcional — solo si quieres que el siguiente turno tenga la nota
git add desempeno-hoy/NOTAS_SMOKE.md
git commit -m "Notas smoke test SQL desempeno-hoy (borrar antes de merge final)"
```

---

## Task 3: Escribir `query.sql` final (parametrizable por país)

**Files:**
- Modify: `desempeno-hoy/query.sql`

**Goal:** una sola query con placeholders `__TIG__`, `__HIST__`, `__ID_COL__`, `__STATE_COL__`, `__FECHA_COL__`, `__TZ_OFFSET__` que el workflow reemplaza por país. Devuelve filas `(fecha_local, hora_1_24, fuente_label, calificados)`.

- [ ] **Step 1: Escribir la query con placeholders**

```sql
-- desempeno-hoy/query.sql
-- Placeholders reemplazados por el workflow:
--   __TIG__         tabla_inmuebles_general del país
--   __HIST__        histórico de estado MM del país
--   __ID_COL__      columna del id de negocio en __HIST__ (negocio_id en CO, deal_id en MX)
--   __STATE_COL__   estado_id (CO) o state_id (MX)
--   __FECHA_COL__   fecha_creacion (CO) o date_create (MX) — confirmar en Task 2
--   __TZ_OFFSET__   -5 (CO) o -6 (MX, sin DST)
WITH lead_fuente AS (
  SELECT
    nid,
    CASE fuente_id
      WHEN 3  THEN 'WEB'
      WHEN 7  THEN 'Habimetro'
      WHEN 20 THEN 'CRM'
      WHEN 35 THEN 'Comercial'
      WHEN 39 THEN 'Broker'
      WHEN 46 THEN 'Propiedades'
      WHEN 47 THEN 'Leadforms'
      WHEN 37 THEN 'Leadforms'
      WHEN 41 THEN 'Leadforms'
      WHEN 42 THEN 'Leadforms'
    END AS fuente_label
  FROM `__TIG__`
  WHERE fecha_creacion >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
    AND nid IS NOT NULL
    AND fuente_id IN (3,7,20,35,37,39,41,42,46,47)
),
primer_calif AS (
  SELECT
    __ID_COL__ AS nid,
    MIN(__FECHA_COL__) AS ts_calif_utc
  FROM `__HIST__`
  WHERE __STATE_COL__ IN (20, 63)
    AND __FECHA_COL__ >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 40 DAY)
  GROUP BY 1
)
SELECT
  DATE(TIMESTAMP_ADD(p.ts_calif_utc, INTERVAL __TZ_OFFSET__ HOUR)) AS fecha_local,
  EXTRACT(HOUR FROM TIMESTAMP_ADD(p.ts_calif_utc, INTERVAL __TZ_OFFSET__ HOUR)) + 1 AS hora_1_24,
  f.fuente_label,
  COUNT(DISTINCT p.nid) AS calificados
FROM primer_calif p
JOIN lead_fuente f USING (nid)
WHERE f.fuente_label IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
```

- [ ] **Step 2: Smoke test del template (CO)**

```bash
cd ~/habi/tableros-marketing
sed -e 's|__TIG__|papyrus-data.habi_wh_bi.tabla_inmuebles_general|g' \
    -e 's|__HIST__|sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2|g' \
    -e 's|__ID_COL__|negocio_id|g' \
    -e 's|__STATE_COL__|estado_id|g' \
    -e 's|__FECHA_COL__|fecha_creacion|g' \
    -e 's|__TZ_OFFSET__|-5|g' \
    desempeno-hoy/query.sql > /tmp/dq_co.sql

bq query --use_legacy_sql=false --format=json --max_rows=20000 < /tmp/dq_co.sql > /tmp/dq_co.json
wc -l /tmp/dq_co.json
head -c 500 /tmp/dq_co.json
```

Expected: el JSON tiene entre cientos y bajas decenas de miles de filas (≈ 40 días × 24h × 6 fuentes = hasta 5,760 combinaciones; menos en práctica por horas sin actividad).

- [ ] **Step 3: Smoke test del template (MX)**

```bash
sed -e 's|__TIG__|papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general|g' \
    -e 's|__HIST__|sellers-main-prod.mx_rds_staging.habi_db_history_state|g' \
    -e 's|__ID_COL__|deal_id|g' \
    -e 's|__STATE_COL__|state_id|g' \
    -e 's|__FECHA_COL__|fecha_creacion|g' \
    -e 's|__TZ_OFFSET__|-6|g' \
    desempeno-hoy/query.sql > /tmp/dq_mx.sql

bq query --use_legacy_sql=false --format=json --max_rows=20000 < /tmp/dq_mx.sql > /tmp/dq_mx.json
wc -l /tmp/dq_mx.json
head -c 500 /tmp/dq_mx.json
```

Si el JOIN MX devuelve 0 (porque `deal_id` no mapea a `nid` directo), ajustar la query a hacer JOIN intermedio con `habi_db_property_deal`. Volver a correr.

- [ ] **Step 4: Borrar NOTAS_SMOKE.md si existe**

```bash
rm -f desempeno-hoy/NOTAS_SMOKE.md
```

- [ ] **Step 5: Commit**

```bash
git add desempeno-hoy/query.sql
git commit -m "SQL desempeno-hoy: query parametrizable por pais (CO/MX) con primer entrance a 20/63"
```

---

## Task 4: Script Python `build_data.py`

**Files:**
- Create: `scripts/desempeno_hoy_to_json.py`

**Goal:** recibe 2 JSON (uno CO, otro MX) generados por `bq query --format=json` + el `weekday` de hoy local + las fechas, y escribe `desempeno-hoy/data.json` con el shape de la sección 3 del spec.

- [ ] **Step 1: Crear el script**

```python
#!/usr/bin/env python3
"""
Construye desempeno-hoy/data.json desde 2 salidas BQ (CO + MX).

Input shape (de `bq query --format=json`):
  list of {"fecha_local": "YYYY-MM-DD", "hora_1_24": int (1..24),
           "fuente_label": str, "calificados": int}

Output: ver spec §3.

Uso:
  desempeno_hoy_to_json.py <co_bq.json> <mx_bq.json> <out_data.json>
"""
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

SOURCES = ["WEB", "Habimetro", "Leadforms", "CRM", "Propiedades", "Broker", "Comercial"]
TZ_OFFSET = {"co": -5, "mx": -6}


def empty_24():
    return [0] * 24


def empty_24_nullable():
    return [None] * 24


def build_country(rows, country):
    """rows: lista bruta de BQ. country: 'co' o 'mx'."""
    tz = TZ_OFFSET[country]
    today_local = (datetime.now(timezone.utc) + timedelta(hours=tz)).date()
    today_weekday = today_local.weekday()  # 0=lun..6=dom

    # Indexar por (fecha_local, fuente) -> array 24
    by_date_src = defaultdict(empty_24)
    for r in rows:
        d = date.fromisoformat(r["fecha_local"])
        s = r["fuente_label"]
        h = int(r["hora_1_24"]) - 1  # 0..23
        n = int(r["calificados"])
        if s not in SOURCES:
            continue
        by_date_src[(d, s)][h] = n

    # Sources que aplican a este país
    if country == "co":
        country_sources = ["WEB", "Habimetro", "Leadforms", "CRM", "Broker", "Comercial"]
    else:
        country_sources = ["WEB", "Habimetro", "Leadforms", "Propiedades", "Broker", "Comercial"]

    # Today: arrays con null para horas futuras (>= current hour local + 1)
    now_local = datetime.now(timezone.utc) + timedelta(hours=tz)
    current_hour_idx = now_local.hour  # 0..23; horas con índice > current_hour_idx están "en el futuro"
    by_hour_today = {}
    for s in country_sources:
        arr = list(by_date_src.get((today_local, s), empty_24()))
        for i in range(current_hour_idx + 1, 24):
            arr[i] = None
        by_hour_today[s] = arr

    # prev_week: mismo weekday hace 7 días
    prev_week_date = today_local - timedelta(days=7)
    by_hour_prev = {s: list(by_date_src.get((prev_week_date, s), empty_24())) for s in country_sources}

    # avg_4_weekdays: media de 4 mismos-weekdays anteriores a prev_week (-14,-21,-28,-35d)
    avg_dates = [today_local - timedelta(days=14 + 7 * i) for i in range(4)]
    by_hour_avg = {}
    for s in country_sources:
        sums = [0.0] * 24
        for d in avg_dates:
            arr = by_date_src.get((d, s), empty_24())
            for i in range(24):
                sums[i] += arr[i]
        by_hour_avg[s] = [round(v / 4.0, 2) for v in sums]

    # Totales
    def sum_arr(arr):
        return sum(v for v in arr if v is not None)

    totals_today = {s: sum_arr(by_hour_today[s]) for s in country_sources}
    totals_today["_all"] = sum(totals_today.values())
    totals_prev = {s: sum_arr(by_hour_prev[s]) for s in country_sources}
    totals_prev["_all"] = sum(totals_prev.values())
    totals_avg = {s: round(sum_arr(by_hour_avg[s]), 2) for s in country_sources}
    totals_avg["_all"] = round(sum(totals_avg.values()), 2)

    return {
        "today_date": today_local.isoformat(),
        "today_weekday": today_weekday,
        "sources": country_sources,
        "by_hour": {
            "today": by_hour_today,
            "prev_week": by_hour_prev,
            "avg_4_weekdays": by_hour_avg,
        },
        "totals": {
            "today_so_far": totals_today,
            "prev_week": totals_prev,
            "avg_4_weekdays": totals_avg,
        },
    }


def main():
    if len(sys.argv) != 4:
        print("Uso: desempeno_hoy_to_json.py <co_bq.json> <mx_bq.json> <out.json>",
              file=sys.stderr)
        sys.exit(1)
    co_path, mx_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(co_path) as f:
        co_rows = json.load(f)
    with open(mx_path) as f:
        mx_rows = json.load(f)

    # generated_at en TZ CO (-5)
    now_utc = datetime.now(timezone.utc)
    now_co = now_utc + timedelta(hours=-5)
    generated_at = now_co.strftime("%Y-%m-%dT%H:%M:%S-05:00")

    out = {
        "generated_at_iso": generated_at,
        "co": build_country(co_rows, "co"),
        "mx": build_country(mx_rows, "mx"),
    }
    with open(out_path, "w") as f:
        json.dump(out, f, separators=(",", ":"))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Hacer ejecutable**

```bash
chmod +x scripts/desempeno_hoy_to_json.py
```

- [ ] **Step 3: Probar con los outputs del Task 3**

```bash
python3 scripts/desempeno_hoy_to_json.py /tmp/dq_co.json /tmp/dq_mx.json /tmp/dq_out.json
python3 -c "import json; d=json.load(open('/tmp/dq_out.json')); print('keys:', list(d.keys())); print('CO sources:', d['co']['sources']); print('CO today_date:', d['co']['today_date']); print('CO totals:', d['co']['totals']); print('MX totals:', d['mx']['totals'])"
```

Expected:
- `keys: ['generated_at_iso', 'co', 'mx']`
- `CO sources` = 6 etiquetas con CRM, MX con Propiedades.
- `CO today_date` = fecha de hoy en CO.
- `totals.today_so_far._all` debe ser un número plausible (> 0 si ya pasaron horas hábiles, puede ser 0 muy temprano).

- [ ] **Step 4: Validar que las horas futuras de "today" son null**

```bash
python3 -c "
import json
d = json.load(open('/tmp/dq_out.json'))
arr = d['co']['by_hour']['today']['WEB']
print('CO WEB today:', arr)
print('count null:', sum(1 for x in arr if x is None))
print('count num:', sum(1 for x in arr if x is not None))
"
```

Expected: el conteo de null debe ser `(24 - current_hour_co - 1)`. Por ejemplo si en CO son las 14:30, hay 9 nulls (horas 16-24 del eje, índices 15..23).

- [ ] **Step 5: Commit**

```bash
git add scripts/desempeno_hoy_to_json.py
git commit -m "Script desempeno_hoy_to_json: BQ output (CO+MX) -> data.json"
```

---

## Task 5: GitHub Actions workflow `desempeno-hoy.yml`

**Files:**
- Create: `.github/workflows/desempeno-hoy.yml`

- [ ] **Step 1: Crear el workflow**

```yaml
# .github/workflows/desempeno-hoy.yml
name: Desempeño hoy (live data)

on:
  schedule:
    - cron: '*/15 * * * *'
  workflow_dispatch:

concurrency:
  group: desempeno-hoy
  cancel-in-progress: true

jobs:
  refresh:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4

      - uses: google-github-actions/setup-gcloud@v2

      - name: Authenticate with user credentials
        run: |
          echo '${{ secrets.GCP_CREDENTIALS }}' > /tmp/adc.json
          gcloud config set project ${{ secrets.GCP_PROJECT }}
          echo "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE=/tmp/adc.json" >> $GITHUB_ENV
          echo "GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json" >> $GITHUB_ENV

      - name: Render and run CO query
        run: |
          sed -e 's|__TIG__|papyrus-data.habi_wh_bi.tabla_inmuebles_general|g' \
              -e 's|__HIST__|sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2|g' \
              -e 's|__ID_COL__|negocio_id|g' \
              -e 's|__STATE_COL__|estado_id|g' \
              -e 's|__FECHA_COL__|fecha_creacion|g' \
              -e 's|__TZ_OFFSET__|-5|g' \
              desempeno-hoy/query.sql > /tmp/dq_co.sql
          bq query --use_legacy_sql=false --format=json --max_rows=50000 < /tmp/dq_co.sql > /tmp/dq_co.json
          echo "CO rows: $(wc -l < /tmp/dq_co.json)"

      - name: Render and run MX query
        run: |
          sed -e 's|__TIG__|papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general|g' \
              -e 's|__HIST__|sellers-main-prod.mx_rds_staging.habi_db_history_state|g' \
              -e 's|__ID_COL__|deal_id|g' \
              -e 's|__STATE_COL__|state_id|g' \
              -e 's|__FECHA_COL__|fecha_creacion|g' \
              -e 's|__TZ_OFFSET__|-6|g' \
              desempeno-hoy/query.sql > /tmp/dq_mx.sql
          bq query --use_legacy_sql=false --format=json --max_rows=50000 < /tmp/dq_mx.sql > /tmp/dq_mx.json
          echo "MX rows: $(wc -l < /tmp/dq_mx.json)"

      - name: Build data.json
        run: |
          python3 scripts/desempeno_hoy_to_json.py /tmp/dq_co.json /tmp/dq_mx.json desempeno-hoy/data.json
          python3 -c "import json; d=json.load(open('desempeno-hoy/data.json')); print('generated:', d['generated_at_iso']); print('co totals:', d['co']['totals']['today_so_far']); print('mx totals:', d['mx']['totals']['today_so_far'])"

      - name: Commit if changed
        run: |
          git config user.email "actions@github.com"
          git config user.name "github-actions[bot]"
          git add desempeno-hoy/data.json
          if git diff --cached --quiet; then
            echo "No changes to commit."
          else
            git commit -m "data: refresh desempeno-hoy $(date -u +%Y-%m-%dT%H:%MZ)"
            git push
          fi
```

- [ ] **Step 2: Ajustar nombres de columnas reales**

Si en Task 2 detectaste que en CO la columna es `estado_id` (no `state_id`), ya está bien. Si en MX la columna de fecha es `date_create` y no `fecha_creacion`, ajustar el `sed` MX a `'s|__FECHA_COL__|date_create|g'`. Verificar antes de commitear.

- [ ] **Step 3: Validar el workflow localmente con act (opcional)**

Si tienes `act` instalado, simular. Si no, mejor probar tras push con `workflow_dispatch`. Saltar este paso si no hay manera fácil de probarlo local — irá en Task 8.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/desempeno-hoy.yml
git commit -m "Workflow desempeno-hoy.yml: cron */15 min CO+MX -> data.json"
```

---

## Task 6: Frontend — esqueleto HTML + CSS

**Files:**
- Modify: `desempeno-hoy/index.html`

**Goal:** estructura visual completa (header, selectors, KPI cards, canvas, footer) con CSS dark theme. Sin lógica JS todavía — placeholders estáticos.

- [ ] **Step 1: Escribir el HTML inicial completo**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📢</text></svg>">
  <title>Desempeño hoy · Tableros Marketing</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a; color: #f8fafc; padding: 24px; min-height: 100vh;
    }
    .back-link {
      color: #94a3b8; text-decoration: none; font-size: 14px;
      display: inline-block; margin-bottom: 16px;
    }
    .back-link:hover { color: #f8fafc; }

    header.titlebar {
      display: flex; align-items: baseline; justify-content: space-between;
      gap: 16px; flex-wrap: wrap; margin-bottom: 8px;
    }
    h1 { font-size: 24px; font-weight: 600; }
    .subtitle { color: #94a3b8; font-size: 13px; margin-bottom: 20px; }

    .freshness {
      display: flex; align-items: center; gap: 8px;
      font-size: 12px; color: #94a3b8;
    }
    .freshness .pill {
      background: #1e293b; border: 1px solid #334155; padding: 4px 10px;
      border-radius: 999px;
    }
    .freshness button.reload {
      background: #1e293b; border: 1px solid #334155; color: #f8fafc;
      padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 12px;
    }
    .freshness button.reload:hover { border-color: #818cf8; }

    .selectors {
      display: flex; gap: 24px; flex-wrap: wrap;
      background: #1e293b; border: 1px solid #334155; border-radius: 12px;
      padding: 16px; margin-bottom: 20px;
    }
    .selector-group { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .selector-group label {
      font-size: 12px; color: #94a3b8; text-transform: uppercase;
      letter-spacing: 0.5px; font-weight: 600; margin-right: 4px;
    }
    .chip {
      background: #0f172a; border: 1px solid #334155; color: #e2e8f0;
      padding: 6px 12px; border-radius: 999px; cursor: pointer; font-size: 13px;
      transition: all 0.1s;
    }
    .chip:hover { border-color: #818cf8; }
    .chip.active { background: #818cf8; color: #0f172a; border-color: #818cf8; font-weight: 600; }

    .kpis {
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px;
    }
    @media (max-width: 900px) { .kpis { grid-template-columns: repeat(2, 1fr); } }
    .kpi-card {
      background: #1e293b; border: 1px solid #334155; border-radius: 12px;
      padding: 16px;
    }
    .kpi-label {
      font-size: 11px; color: #94a3b8; text-transform: uppercase;
      letter-spacing: 0.5px; font-weight: 600;
    }
    .kpi-value { font-size: 32px; font-weight: 700; margin-top: 4px; }
    .kpi-delta { font-size: 12px; margin-top: 6px; color: #94a3b8; }
    .kpi-delta.up { color: #4ade80; }
    .kpi-delta.down { color: #f87171; }

    .chart-card {
      background: #1e293b; border: 1px solid #334155; border-radius: 12px;
      padding: 20px; margin-bottom: 24px;
    }
    .chart-card h2 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
    .chart-wrap { position: relative; height: 420px; }

    footer.notas {
      color: #64748b; font-size: 12px; line-height: 1.6;
      border-top: 1px solid #1e293b; padding-top: 16px;
    }
    .empty-state, .warn-banner {
      text-align: center; padding: 32px; color: #94a3b8;
      background: #1e293b; border: 1px solid #334155; border-radius: 12px;
    }
    .warn-banner { color: #fbbf24; border-color: #78350f; background: #422006; margin-bottom: 16px; }
  </style>
</head>
<body>
  <a href="../" class="back-link">← Volver (Tableros Marketing Sellers)</a>

  <header class="titlebar">
    <div>
      <h1>Desempeño hoy · Calificados</h1>
      <div class="subtitle">Calificados MM (estados 20/63) — primer entrance — hora local del país</div>
    </div>
    <div class="freshness">
      <span class="pill" id="last-update">Cargando…</span>
      <button class="reload" id="btn-reload">⟳ Recargar</button>
    </div>
  </header>

  <div id="warn-banner" class="warn-banner" hidden>⚠ Datos retrasados — última corrida hace más de 45 min</div>

  <div class="selectors">
    <div class="selector-group">
      <label>País</label>
      <button class="chip active" data-pais="co">CO</button>
      <button class="chip" data-pais="mx">MX</button>
    </div>
    <div class="selector-group">
      <label>Vista</label>
      <button class="chip active" data-vista="acumulado">Acumulado</button>
      <button class="chip" data-vista="por_hora">Por hora</button>
    </div>
    <div class="selector-group" id="fuentes-group">
      <label>Fuentes</label>
      <button class="chip toggle-all active" id="chip-todas">Todas</button>
      <!-- chips de fuentes se inyectan al cargar -->
    </div>
  </div>

  <div class="kpis">
    <div class="kpi-card">
      <div class="kpi-label">Hoy hasta ahora</div>
      <div class="kpi-value" id="kpi-hoy">—</div>
      <div class="kpi-delta" id="kpi-hoy-delta">vs prom: —</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Mismo día sem. pasada (total)</div>
      <div class="kpi-value" id="kpi-prev">—</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Prom. últimos 4 (total)</div>
      <div class="kpi-value" id="kpi-avg">—</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Ritmo hora actual</div>
      <div class="kpi-value" id="kpi-ritmo">—</div>
      <div class="kpi-delta" id="kpi-ritmo-delta">vs prom hora: —</div>
    </div>
  </div>

  <div class="chart-card">
    <h2 id="chart-title">Calificados por hora — Acumulado</h2>
    <div class="chart-wrap"><canvas id="chart-main"></canvas></div>
  </div>

  <footer class="notas">
    Fuente: <code>tabla_inmuebles_general</code> + <code>historico_estado_v2</code> (MM). Delay típico de BQ 30 min – 2 h.
    Workflow corre cada 15 min UTC. Hora local del país seleccionado (CO UTC-5, MX UTC-6, sin DST).
  </footer>

  <script>
    // Placeholder. La lógica completa va en Task 7.
    document.getElementById('last-update').textContent = 'Sin datos';
  </script>
</body>
</html>
```

- [ ] **Step 2: Abrir local y verificar visualmente**

```bash
cd ~/habi/tableros-marketing
python3 -m http.server 8000 &
SERVER_PID=$!
sleep 1
echo "Abrir http://localhost:8000/desempeno-hoy/ en el browser"
# Cuando termines, kill $SERVER_PID
```

Verificar: layout dark, header con título, pill de actualización, selectors row con chips CO/MX/Acumulado/Por hora/Todas, 4 KPI cards, canvas vacío, footer. Sin errores en consola (Chart.js cargado).

- [ ] **Step 3: Cerrar el server**

```bash
kill $SERVER_PID 2>/dev/null || true
```

- [ ] **Step 4: Commit**

```bash
git add desempeno-hoy/index.html
git commit -m "Frontend desempeno-hoy: HTML + CSS dark theme con selectors y KPI cards"
```

---

## Task 7: Frontend — lógica completa (fetch, filtros, chart, KPIs, toggle)

**Files:**
- Modify: `desempeno-hoy/index.html` (reemplazar el `<script>` placeholder)

- [ ] **Step 1: Reemplazar el bloque `<script>` por la lógica completa**

Buscar el bloque `<script>` actual (placeholder) y reemplazarlo entero por:

```html
  <script>
    // ============================================================
    // Estado global
    // ============================================================
    const state = {
      data: null,           // contenido de data.json
      pais: 'co',
      vista: 'acumulado',   // 'acumulado' | 'por_hora'
      fuentes: new Set(),   // fuentes seleccionadas; vacío = ninguna
    };
    let chartInstance = null;

    const WEEKDAY_LABELS = ['lun', 'mar', 'mie', 'jue', 'vie', 'sab', 'dom'];

    // ============================================================
    // Fetch data.json con cache-bust
    // ============================================================
    async function loadData() {
      try {
        const url = 'data.json?t=' + Date.now();
        const r = await fetch(url, { cache: 'no-store' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        state.data = await r.json();
        applyFreshness();
        renderFuentes();
        render();
      } catch (e) {
        document.getElementById('last-update').textContent = 'Error al cargar';
        console.error(e);
      }
    }

    // ============================================================
    // Frescura: pill + banner
    // ============================================================
    function applyFreshness() {
      const iso = state.data.generated_at_iso;
      const generated = new Date(iso);
      const now = new Date();
      const diffMin = Math.round((now - generated) / 60000);
      let txt;
      if (diffMin < 1) txt = 'hace <1 min';
      else if (diffMin < 60) txt = 'hace ' + diffMin + ' min';
      else txt = 'hace ' + Math.floor(diffMin / 60) + 'h ' + (diffMin % 60) + 'min';
      document.getElementById('last-update').textContent = 'Última actualización: ' + txt;
      document.getElementById('warn-banner').hidden = diffMin <= 45;
    }

    // ============================================================
    // Selector de fuentes (chips inyectados según país)
    // ============================================================
    function renderFuentes() {
      const group = document.getElementById('fuentes-group');
      // Borrar chips de fuente (todas las que no son "Todas")
      [...group.querySelectorAll('.chip:not(.toggle-all)')].forEach(c => c.remove());
      const sources = state.data[state.pais].sources;
      state.fuentes = new Set(sources);  // default: todas seleccionadas
      for (const s of sources) {
        const c = document.createElement('button');
        c.className = 'chip active';
        c.dataset.fuente = s;
        c.textContent = s;
        c.addEventListener('click', () => toggleFuente(s, c));
        group.appendChild(c);
      }
      document.getElementById('chip-todas').classList.add('active');
    }

    function toggleFuente(s, chipEl) {
      if (state.fuentes.has(s)) state.fuentes.delete(s);
      else state.fuentes.add(s);
      chipEl.classList.toggle('active');
      // El chip "Todas" se mantiene activo solo si todas las fuentes están seleccionadas
      const allOn = state.fuentes.size === state.data[state.pais].sources.length;
      document.getElementById('chip-todas').classList.toggle('active', allOn);
      render();
    }

    function toggleTodas() {
      const sources = state.data[state.pais].sources;
      const allOn = state.fuentes.size === sources.length;
      if (allOn) {
        state.fuentes.clear();
        document.querySelectorAll('#fuentes-group .chip:not(.toggle-all)').forEach(c => c.classList.remove('active'));
        document.getElementById('chip-todas').classList.remove('active');
      } else {
        state.fuentes = new Set(sources);
        document.querySelectorAll('#fuentes-group .chip:not(.toggle-all)').forEach(c => c.classList.add('active'));
        document.getElementById('chip-todas').classList.add('active');
      }
      render();
    }

    // ============================================================
    // Cálculos derivados
    // ============================================================
    function sumByHourFiltered(series) {
      // series: { fuente_label: [24 nums o null] }
      // Si todas las fuentes están seleccionadas y existe "_all", podría usarse, pero
      // _all está en totals, no en by_hour. Aquí sumamos client-side siempre.
      const sources = [...state.fuentes];
      const out = new Array(24).fill(0);
      let hasNull = new Array(24).fill(false);
      for (const s of sources) {
        const arr = series[s] || [];
        for (let i = 0; i < 24; i++) {
          if (arr[i] === null || arr[i] === undefined) hasNull[i] = true;
          else out[i] += arr[i];
        }
      }
      // Si todas las fuentes seleccionadas dicen null en esa hora → la suma es null
      // (asumimos que series tienen null sólo en "today" para horas futuras → todas las fuentes lo tienen)
      const nullForAll = new Array(24).fill(false);
      for (let i = 0; i < 24; i++) {
        const allNull = sources.every(s => (series[s] || [])[i] === null || (series[s] || [])[i] === undefined);
        if (allNull && sources.length > 0) nullForAll[i] = true;
      }
      return out.map((v, i) => nullForAll[i] ? null : v);
    }

    function toCumulative(arr) {
      let acc = 0;
      return arr.map(v => {
        if (v === null || v === undefined) return null;
        acc += v;
        return acc;
      });
    }

    function sumValid(arr) {
      return arr.reduce((s, v) => s + (v == null ? 0 : v), 0);
    }

    // ============================================================
    // Render principal
    // ============================================================
    function render() {
      if (!state.data) return;
      const p = state.data[state.pais];
      const todayHr = sumByHourFiltered(p.by_hour.today);
      const prevHr  = sumByHourFiltered(p.by_hour.prev_week);
      const avgHr   = sumByHourFiltered(p.by_hour.avg_4_weekdays);

      let todaySer, prevSer, avgSer;
      if (state.vista === 'acumulado') {
        todaySer = toCumulative(todayHr);
        prevSer = toCumulative(prevHr);
        avgSer = toCumulative(avgHr);
      } else {
        todaySer = todayHr;
        prevSer = prevHr;
        avgSer = avgHr;
      }

      // KPIs
      const totalHoy = sumValid(todayHr);
      const totalPrev = sumValid(prevHr);
      const totalAvg = +sumValid(avgHr).toFixed(1);
      document.getElementById('kpi-hoy').textContent = totalHoy.toLocaleString('es-CO');
      document.getElementById('kpi-prev').textContent = totalPrev.toLocaleString('es-CO');
      document.getElementById('kpi-avg').textContent = totalAvg.toLocaleString('es-CO');

      // Ritmo hora actual: último índice no-null de today
      let lastIdx = -1;
      for (let i = 0; i < 24; i++) if (todayHr[i] !== null && todayHr[i] !== undefined) lastIdx = i;
      const ritmoHoy = lastIdx >= 0 ? todayHr[lastIdx] : 0;
      const ritmoAvg = lastIdx >= 0 ? avgHr[lastIdx] : 0;
      document.getElementById('kpi-ritmo').textContent = ritmoHoy.toLocaleString('es-CO') + ' /h';
      const dRitmo = ritmoAvg > 0 ? ((ritmoHoy - ritmoAvg) / ritmoAvg * 100).toFixed(0) : 0;
      const deltaR = document.getElementById('kpi-ritmo-delta');
      deltaR.textContent = 'vs prom hora: ' + (dRitmo >= 0 ? '+' : '') + dRitmo + '%';
      deltaR.className = 'kpi-delta ' + (dRitmo >= 0 ? 'up' : 'down');

      // KPI hoy delta: hoy vs prom proyectado al mismo punto del día
      const promAtCurrent = lastIdx >= 0 ? (state.vista === 'acumulado' ? avgSer[lastIdx] : sumValid(avgHr.slice(0, lastIdx + 1))) : 0;
      const dHoy = promAtCurrent > 0 ? ((totalHoy - promAtCurrent) / promAtCurrent * 100).toFixed(0) : 0;
      const deltaH = document.getElementById('kpi-hoy-delta');
      deltaH.textContent = 'vs prom al mismo punto: ' + (dHoy >= 0 ? '+' : '') + dHoy + '%';
      deltaH.className = 'kpi-delta ' + (dHoy >= 0 ? 'up' : 'down');

      // Título chart
      const wdLabel = WEEKDAY_LABELS[p.today_weekday];
      const vistaLabel = state.vista === 'acumulado' ? 'Acumulado' : 'Por hora';
      document.getElementById('chart-title').textContent = 'Calificados por hora — ' + vistaLabel;

      // Chart
      const labels = Array.from({length: 24}, (_, i) => String(i + 1));
      const datasets = [
        {
          label: 'Hoy',
          data: todaySer,
          borderColor: '#818cf8',
          backgroundColor: '#818cf8',
          borderWidth: 3, tension: 0.25,
          spanGaps: false,
        },
        {
          label: 'Hace 7 días (mismo ' + wdLabel + ')',
          data: prevSer,
          borderColor: '#94a3b8', borderDash: [6, 4],
          borderWidth: 2, tension: 0.25, pointRadius: 0,
          backgroundColor: 'transparent',
        },
        {
          label: 'Prom. 4 últimos ' + wdLabel,
          data: avgSer,
          borderColor: '#fbbf24', borderDash: [3, 3],
          borderWidth: 2, tension: 0.25, pointRadius: 0,
          backgroundColor: 'transparent',
        },
      ];

      if (chartInstance) chartInstance.destroy();
      const ctx = document.getElementById('chart-main').getContext('2d');
      chartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { labels: { color: '#e2e8f0', font: { size: 12 } } },
            tooltip: {
              backgroundColor: '#0f172a',
              borderColor: '#334155',
              borderWidth: 1,
              titleColor: '#f8fafc',
              bodyColor: '#e2e8f0',
              callbacks: {
                title: (items) => 'Hora ' + items[0].label,
              },
            },
          },
          scales: {
            x: {
              ticks: { color: '#94a3b8' },
              grid: { color: '#1e293b' },
              title: { display: true, text: 'Hora local (1-24)', color: '#94a3b8' },
            },
            y: {
              beginAtZero: true,
              ticks: { color: '#94a3b8' },
              grid: { color: '#1e293b' },
              title: { display: true, text: state.vista === 'acumulado' ? 'Calificados acumulados' : 'Calificados / hora', color: '#94a3b8' },
            },
          },
        },
      });
    }

    // ============================================================
    // Wiring de selectors
    // ============================================================
    document.querySelectorAll('.chip[data-pais]').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('.chip[data-pais]').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
        state.pais = el.dataset.pais;
        renderFuentes();
        render();
      });
    });
    document.querySelectorAll('.chip[data-vista]').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('.chip[data-vista]').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
        state.vista = el.dataset.vista;
        render();
      });
    });
    document.getElementById('chip-todas').addEventListener('click', toggleTodas);
    document.getElementById('btn-reload').addEventListener('click', loadData);

    // Auto-refresh suave cada 5 min para detectar nueva data
    setInterval(loadData, 5 * 60 * 1000);

    // Carga inicial
    loadData();
  </script>
```

- [ ] **Step 2: Generar un data.json de prueba local**

Si `desempeno-hoy/data.json` no existe todavía, generar uno con la salida del Task 4:

```bash
cp /tmp/dq_out.json ~/habi/tableros-marketing/desempeno-hoy/data.json
```

- [ ] **Step 3: Servir y probar end-to-end local**

```bash
cd ~/habi/tableros-marketing
python3 -m http.server 8000 &
SERVER_PID=$!
sleep 1
echo "Abrir http://localhost:8000/desempeno-hoy/"
# Validar:
#  - KPI cards muestran números reales
#  - Chart muestra 3 líneas (hoy sólida, hace 7d gris punteada, prom 4 ámbar punteada)
#  - Línea de hoy se corta a la hora actual
#  - Toggle Acumulado/Por hora cambia el shape
#  - Toggle CO/MX cambia los datos y las fuentes visibles (CRM <-> Propiedades)
#  - Deseleccionar una fuente recalcula KPIs y chart
#  - Botón ⟳ Recargar dispara un fetch (validar en Network)
#  - "Última actualización: hace X min" se muestra correctamente
```

- [ ] **Step 4: Cerrar el server**

```bash
kill $SERVER_PID 2>/dev/null || true
```

- [ ] **Step 5: Commit (NO incluir data.json — eso lo genera el workflow en prod)**

```bash
# Si copiaste data.json de prueba, removerlo del staging
git checkout -- desempeno-hoy/data.json 2>/dev/null || rm -f desempeno-hoy/data.json
git add desempeno-hoy/index.html
git commit -m "Frontend desempeno-hoy: logica completa (fetch, filtros, chart 3 series, KPIs, toggle)"
```

---

## Task 8: Card en landing + deploy + verificación en live

**Files:**
- Modify: `index.html` (raíz)

- [ ] **Step 1: Encontrar el bloque de cards en el landing**

```bash
grep -n '"card"' ~/habi/tableros-marketing/index.html | head -20
```

Localizar la última `<a class="card">` dentro de la sección "Tableros" (no la de docs, no la de hub). Las nuevas van **al final** (regla `feedback_hub_orden`).

- [ ] **Step 2: Agregar la card nueva al final del bloque "Tableros"**

Después de la última `<a class="card">` y antes del cierre del contenedor, insertar (ajustar la clase/markup al patrón exacto que use el repo):

```html
        <a class="card" href="desempeno-hoy/">
          <div class="card-emoji">⏱️</div>
          <div class="card-title">Desempeño hoy</div>
          <div class="card-desc">Calificados MM live, hora-por-hora, CO+MX con comparativo hoy vs hace 7 días vs prom 4 semanas.</div>
        </a>
```

- [ ] **Step 3: Validar landing local**

```bash
python3 -m http.server 8000 &
SERVER_PID=$!
sleep 1
echo "Abrir http://localhost:8000/ y validar que la card aparece al final de Tableros y que el click va a desempeno-hoy/"
```

```bash
kill $SERVER_PID 2>/dev/null || true
```

- [ ] **Step 4: Commit y push**

```bash
git add index.html
git commit -m "Landing: agregar card Desempeno hoy al final de Tableros"
git push origin main
```

- [ ] **Step 5: Disparar el workflow manualmente la primera vez**

Abrir GitHub → Actions → "Desempeño hoy (live data)" → Run workflow → main. Verificar que termina OK y commitea `desempeno-hoy/data.json`.

```bash
# Alternativa CLI con gh
gh workflow run desempeno-hoy.yml --ref main
gh run watch
```

- [ ] **Step 6: Validar en live**

Esperar 1-2 min a que GitHub Pages refresque tras el commit del workflow. Abrir:

```
https://camilootoya-habi.github.io/tableros-marketing-habi/desempeno-hoy/
```

Validar contra el spec §"Verificación post-deploy":
- Chart muestra línea de hoy con datos hasta cerca de la hora actual.
- 2 series comparativas completas (24 puntos cada una).
- Selector país cambia datos (CO ↔ MX).
- Multi-select fuentes recalcula KPIs y chart.
- Toggle Acumulado/Por hora funciona.
- Botón ⟳ recarga el JSON y actualiza el timestamp del pill.
- Pill "Última actualización" muestra <15 min después de la corrida.

- [ ] **Step 7: Verificar que el cron quedó corriendo**

Esperar ~20 min después del Step 5 y refrescar la página. El pill debe actualizar a una hora más nueva. Si no, abrir Actions y ver si hubo errores en el cron.

- [ ] **Step 8: Commit final si hubo ajustes**

Si algo se rompió y hubo que ajustar, commit con un mensaje claro de qué se arregló post-deploy.

---

## Notas de cierre

- **Memoria a actualizar tras éxito:** crear `~/.claude/projects/-home-administrador/memory/habi/tableros/desempeno_hoy.md` con URL, paths, query patterns, frescura observada, hallazgos del primer día live.
- **Métrica de éxito:** que Camilo pueda abrir el tablero a las 11am cualquier día y saber en <10 segundos si vamos por encima o por debajo de un día típico.
- **Si los volúmenes BQ resultan más grandes** de lo previsto (la query devuelve >50K rows), subir `--max_rows` en el workflow y considerar agregar `LIMIT` o particionado.
