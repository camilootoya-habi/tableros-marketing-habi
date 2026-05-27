# Funnel por fuente de lead — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el sub-tablero `funnel-fuentes/` que muestra el funnel de leads desde landing hasta deal en HubSpot, cortado por 3 fuentes (Web habi.co, Help-to-sell, Ayuda Venta Inmo), con vista Funnel y vista Tendencia.

**Architecture:** SQL en BigQuery → JSON estático (generado por workflow diario) → HTML estático con render en JS puro. Atribución a HubSpot vía chain de UUID: `anonymous_id → backbone_uuid → deal_uuid → nid`. Sin backend, sin tests unitarios — validación contra BQ real y verificación manual en browser.

**Tech Stack:** BigQuery (CTE-based SQL), Python 3 (transformer), HTML + vanilla JS + Chart.js (CDN), GitHub Actions (workflow consolidado).

**Spec de referencia:** `docs/superpowers/specs/2026-05-12-funnel-fuentes-design.md`

---

## Notas previas para el ejecutor

- **No hay framework de tests** en este repo. La validación es:
  - Para SQL: correr la query contra BQ real con `bq query` y verificar cantidades/estructura.
  - Para el script Python: probar localmente con la salida real de BQ.
  - Para el frontend: abrir el HTML en navegador (con un mini server local: `python3 -m http.server`) y verificar interacciones.
- **Tabla referencial de leads de validación** (creados durante el diseño): 
  - NID `60055700571` (María Luz, 2026-05-06): chain UUID completo, 7 page events, fuente `help_to_sell`.
  - NID `60173994780` (yajaira, 2026-05-11): `b.uuid = NULL`, 0 page events, fuente `ayuda_venta`.
- **Working directory**: `~/habi/tableros-marketing/` (repo `tableros-marketing-habi`).
- **Convención**: `query.sql` archivo separado, `build_data.py` opcional para transformar BQ→JSON, `data.json` final que el frontend lee, `index.html` con `<style>` inline.
- **No usar emojis** en código ni docs salvo el favicon megáfono (convención del hub).
- **Frequent commits** — cada task termina con un commit aparte.

---

## Task 1: Crear estructura de carpeta y archivos vacíos

**Files:**
- Create: `funnel-fuentes/index.html` (vacío por ahora)
- Create: `funnel-fuentes/query.sql` (vacío por ahora)
- Create: `funnel-fuentes/README.md` (puntero al spec)

- [ ] **Step 1: Crear la carpeta**

```bash
cd ~/habi/tableros-marketing
mkdir -p funnel-fuentes
```

- [ ] **Step 2: Crear archivos placeholder**

```bash
touch funnel-fuentes/index.html funnel-fuentes/query.sql
```

- [ ] **Step 3: Crear README.md con puntero al spec**

```markdown
# funnel-fuentes/

Funnel de leads desde landing hasta deal en HubSpot, cortado por fuente (Web habi.co, Help-to-sell, Ayuda Venta Inmo).

Spec: `docs/superpowers/specs/2026-05-12-funnel-fuentes-design.md`

Live: https://camilootoya-habi.github.io/tableros-marketing-habi/funnel-fuentes/
```

- [ ] **Step 4: Commit inicial**

```bash
git add funnel-fuentes/
git commit -m "Scaffold funnel-fuentes folder (empty index.html, query.sql, README pointer)"
```

---

## Task 2: Construir `query.sql` — CTE 1 (`pages_classified`)

**Files:**
- Modify: `funnel-fuentes/query.sql`

**Goal del CTE:** filtrar `segment.pages` a `/formulario-inmueble/*` y clasificar cada evento como `web_puro` o `help_to_sell`. Ventana = 180 días excluyendo hoy.

- [ ] **Step 1: Escribir el CTE inicial**

```sql
-- funnel-fuentes/query.sql
-- Funnel de leads CO: Web habi.co | Help-to-sell | Ayuda Venta (Inmo).
-- Output: filas (date, source, stage, count) que build_data.py pivotea a data.json.
-- Ventana: últimos 180 días (excluye hoy). Timezone: America/Bogota.

WITH params AS (
  SELECT
    DATE_SUB(CURRENT_DATE('America/Bogota'), INTERVAL 180 DAY) AS start_date,
    CURRENT_DATE('America/Bogota') AS end_date_exclusive
),

pages_classified AS (
  SELECT
    DATE(timestamp, 'America/Bogota') AS d,
    anonymous_id,
    context_page_path AS path,
    context_page_url AS url,
    context_page_referrer AS ref,
    name AS event_name,
    timestamp AS ts,
    CASE
      WHEN context_page_url LIKE '%utm_content=help_to_sell%'
        OR context_page_referrer LIKE '%ayudaventas-habi-web.vercel.app%'
      THEN 'help_to_sell'
      ELSE 'web_puro'
    END AS source
  FROM `sellers-main-prod.co_segment_profiles.pages`, params
  WHERE context_page_path LIKE '/formulario-inmueble%'
    AND DATE(timestamp, 'America/Bogota') >= params.start_date
    AND DATE(timestamp, 'America/Bogota') < params.end_date_exclusive
    AND anonymous_id IS NOT NULL
)

SELECT source, COUNT(DISTINCT anonymous_id) AS unique_visitors, COUNT(*) AS events
FROM pages_classified
GROUP BY source
ORDER BY source;
```

- [ ] **Step 2: Correr el query contra BQ y verificar volumen**

```bash
cd ~/habi/tableros-marketing
bq query --use_legacy_sql=false --format=pretty < funnel-fuentes/query.sql
```

Expected: dos filas (`help_to_sell` y `web_puro`), con `web_puro` órdenes de magnitud mayor que `help_to_sell` (web_puro ~tens of thousands de visitantes, help_to_sell de orden bajo).

- [ ] **Step 3: Si las cifras son razonables, dejar el CTE sin SELECT final y proseguir al siguiente. NO commitear aún (commitearemos query completa al final del Task 5).**

Remplazar el `SELECT source, COUNT...` por un comentario `-- (siguiente CTE)` para preparar el archivo para el siguiente CTE.

---

## Task 3: Construir `query.sql` — CTE 2 (`stages_daily`)

**Files:**
- Modify: `funnel-fuentes/query.sql`

**Goal del CTE:** generar las filas 1-7 del funnel agregadas por día × fuente × stage.

- [ ] **Step 1: Agregar el CTE stages_daily**

```sql
stages_daily AS (
  SELECT
    d,
    source,
    stage,
    COUNT(DISTINCT anonymous_id) AS n
  FROM pages_classified,
  UNNEST([
    STRUCT(
      CASE
        WHEN path = '/formulario-inmueble/direccion' THEN 'direccion'
        WHEN path IN ('/formulario-inmueble/inmuebles-zona',
                      '/formulario-inmueble/confirmar-ubicacion',
                      '/formulario-inmueble/sugerencias') THEN 'zona'
        WHEN path = '/formulario-inmueble/datos-inmueble' THEN 'datos_inmueble'
        WHEN path = '/formulario-inmueble/contacto' THEN 'contacto'
        WHEN path = '/formulario-inmueble/caracteristicas' THEN 'caracteristicas'
        WHEN path = '/formulario-inmueble/ultimos-detalles' THEN 'ultimos_detalles'
        WHEN path = '/formulario-inmueble/felicitaciones' THEN 'felicitaciones'
        ELSE NULL
      END AS stage)
  ])
  WHERE stage IS NOT NULL
  GROUP BY d, source, stage
)
```

Nota: si BigQuery se queja del CROSS JOIN UNNEST con CASE, alternativa equivalente:

```sql
stages_daily AS (
  WITH stage_map AS (
    SELECT path, stage FROM UNNEST([
      STRUCT('/formulario-inmueble/direccion' AS path, 'direccion' AS stage),
      ('/formulario-inmueble/inmuebles-zona', 'zona'),
      ('/formulario-inmueble/confirmar-ubicacion', 'zona'),
      ('/formulario-inmueble/sugerencias', 'zona'),
      ('/formulario-inmueble/datos-inmueble', 'datos_inmueble'),
      ('/formulario-inmueble/contacto', 'contacto'),
      ('/formulario-inmueble/caracteristicas', 'caracteristicas'),
      ('/formulario-inmueble/ultimos-detalles', 'ultimos_detalles'),
      ('/formulario-inmueble/felicitaciones', 'felicitaciones')
    ])
  )
  SELECT
    p.d,
    p.source,
    sm.stage,
    COUNT(DISTINCT p.anonymous_id) AS n
  FROM pages_classified p
  JOIN stage_map sm ON sm.path = p.path
  GROUP BY p.d, p.source, sm.stage
)
```

Usar la segunda versión (más legible y BQ-friendly).

- [ ] **Step 2: Agregar SELECT temporal al final para verificar**

```sql
SELECT * FROM stages_daily
WHERE d >= DATE_SUB(CURRENT_DATE('America/Bogota'), INTERVAL 7 DAY)
ORDER BY d DESC, source, stage;
```

- [ ] **Step 3: Correr contra BQ y verificar que las cifras tienen sentido**

```bash
bq query --use_legacy_sql=false --format=pretty < funnel-fuentes/query.sql
```

Expected: filas con counts decrecientes desde `direccion` (alto) hacia `felicitaciones` (más bajo) para `web_puro`. Para `help_to_sell` cifras bajas pero no cero.

- [ ] **Step 4: Reemplazar el SELECT temporal por comentario para el siguiente CTE.**

---

## Task 4: Construir `query.sql` — CTE 3 (`uuid_chain`) + CTE 4 (`leads_ab_daily`)

**Files:**
- Modify: `funnel-fuentes/query.sql`

**Goal:** construir la cadena UUID y derivar leads creados (fila 8) para fuentes A y B.

- [ ] **Step 1: Agregar uuid_chain CTE (resolución del backbone_uuid por anonymous_id)**

```sql
uuid_chain AS (
  -- Para cada anonymous_id que llegó a /felicitaciones, resolver el deal final vía chain UUID.
  -- Una fila por (anonymous_id, source, fecha_felicitaciones, fecha_creacion_lead) cuando hay match.
  SELECT
    fp.d AS d_form,
    fp.source,
    fp.anonymous_id,
    sc.backbone_uuid,
    b.deal_uuid,
    pd.nid,
    DATE(g.fecha_creacion, 'America/Bogota') AS d_lead
  FROM (
    SELECT d, source, anonymous_id
    FROM pages_classified
    WHERE path = '/formulario-inmueble/felicitaciones'
    GROUP BY d, source, anonymous_id
  ) fp
  LEFT JOIN `sellers-main-prod.co_segment_profiles.select_content` sc
    ON sc.anonymous_id = fp.anonymous_id
    AND DATE(sc.timestamp, 'America/Bogota') = fp.d_form
  LEFT JOIN `sellers-main-prod.top_funnel.web_global_api_business` b
    ON b.uuid = sc.backbone_uuid
  LEFT JOIN `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` pd
    ON pd.uuid = b.deal_uuid
  LEFT JOIN `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g
    ON g.nid = pd.nid
)
```

- [ ] **Step 2: Validar uuid_chain contra el caso de María Luz (NID 60055700571)**

```sql
-- Pega esto al final del query.sql temporalmente
SELECT * FROM uuid_chain
WHERE nid = 60055700571;
```

```bash
bq query --use_legacy_sql=false --format=pretty < funnel-fuentes/query.sql
```

Expected: al menos una fila con `nid=60055700571`, `source='help_to_sell'`, `d_form='2026-05-06'`, `d_lead='2026-05-06'` (o cercanos según TZ).

- [ ] **Step 3: Agregar leads_ab_daily CTE**

```sql
leads_ab_daily AS (
  -- Cuenta de leads creados (en HubSpot/CRM) cuyo /felicitaciones cayó en el mismo día Bogotá.
  SELECT
    d_form AS d,
    source,
    COUNT(DISTINCT nid) AS n
  FROM uuid_chain
  WHERE nid IS NOT NULL
    AND d_lead = d_form  -- match estricto de día Bogotá
  GROUP BY d, source
),

completions_no_deal_daily AS (
  -- Anonymous_ids que llegaron a /felicitaciones pero el chain no resolvió un deal en el mismo día.
  SELECT
    d_form AS d,
    source,
    COUNT(DISTINCT anonymous_id) AS n
  FROM uuid_chain
  WHERE nid IS NULL OR d_lead IS NULL OR d_lead != d_form
  GROUP BY d, source
)
```

- [ ] **Step 4: Verificar con SELECT temporal**

```sql
SELECT 'leads' AS kind, d, source, n FROM leads_ab_daily
WHERE d >= DATE_SUB(CURRENT_DATE('America/Bogota'), INTERVAL 14 DAY)
UNION ALL
SELECT 'no_deal', d, source, n FROM completions_no_deal_daily
WHERE d >= DATE_SUB(CURRENT_DATE('America/Bogota'), INTERVAL 14 DAY)
ORDER BY d DESC, kind, source;
```

```bash
bq query --use_legacy_sql=false --format=pretty < funnel-fuentes/query.sql
```

Expected: para los últimos 14 días debería ver leads creados, sobre todo para `web_puro`, y un puñado de `no_deal` (el gap a investigar después).

- [ ] **Step 5: Quitar SELECT temporal.**

---

## Task 5: Construir `query.sql` — CTE 5 (`leads_c_daily`) y SELECT final UNION ALL

**Files:**
- Modify: `funnel-fuentes/query.sql`

**Goal:** agregar Ayuda Venta (fuente C) y unir todo en un output relacional `(date, source, stage, n)`.

- [ ] **Step 1: Agregar leads_c_daily**

```sql
leads_c_daily AS (
  -- Fuente C (Ayuda Venta - form Inmo en vercel). Sin etapas, solo lead final.
  SELECT
    DATE(createdate, 'America/Bogota') AS d,
    'ayuda_venta' AS source,
    'lead_hubspot' AS stage,
    COUNT(*) AS n
  FROM `sellers-main-prod.hubspot.deals`, params
  WHERE sub_fuente = 'Ayuda Venta'
    AND DATE(createdate, 'America/Bogota') >= params.start_date
    AND DATE(createdate, 'America/Bogota') < params.end_date_exclusive
  GROUP BY d
)
```

- [ ] **Step 2: Agregar SELECT final UNION ALL**

```sql
SELECT d, source, stage, n FROM stages_daily
UNION ALL
SELECT d, source, 'lead_hubspot' AS stage, n FROM leads_ab_daily
UNION ALL
SELECT d, source, stage, n FROM leads_c_daily
UNION ALL
SELECT d, source, 'completions_no_deal' AS stage, n FROM completions_no_deal_daily
ORDER BY d DESC, source, stage;
```

- [ ] **Step 3: Verificar query completo**

```bash
bq query --use_legacy_sql=false --format=pretty --max_rows=200 < funnel-fuentes/query.sql | head -50
```

Expected: filas de varios días con sources mezclados (`web_puro`, `help_to_sell`, `ayuda_venta`) y stages (`direccion`, `zona`, …, `lead_hubspot`, `completions_no_deal`).

- [ ] **Step 4: Validar con NIDs conocidos (María Luz y yajaira)**

```sql
-- Sanity check: el día 2026-05-06 debe haber al menos 1 lead en web_puro/help_to_sell
--   y el 2026-05-11 al menos 1 lead en ayuda_venta.
SELECT d, source, stage, n
FROM (
  -- query completa aquí (todos los CTEs + UNION ALL)
)
WHERE (d = '2026-05-06' AND source IN ('web_puro', 'help_to_sell'))
   OR (d = '2026-05-11' AND source = 'ayuda_venta')
   AND stage = 'lead_hubspot';
```

(En la práctica este check se hace ad-hoc en BQ console, no se commitea.)

- [ ] **Step 5: Commit del query.sql**

```bash
git add funnel-fuentes/query.sql
git commit -m "Add funnel-fuentes query.sql: stages by source + UUID-chain attribution + Ayuda Venta"
```

---

## Task 6: Crear `scripts/funnel_fuentes_to_json.py`

**Files:**
- Create: `scripts/funnel_fuentes_to_json.py`

**Goal:** leer la salida JSON de `bq query` (filas planas) y producir `funnel-fuentes/data.json` en el shape anidado especificado en §7.1 del spec.

- [ ] **Step 1: Escribir el script completo**

```python
#!/usr/bin/env python3
"""
Builds funnel-fuentes/data.json from BQ query output.

Input shape (from `bq query --format=json`):
  list of {"d": "YYYY-MM-DD", "source": "...", "stage": "...", "n": <int>}

Output shape: see spec §7.1.

Usage:
  funnel_fuentes_to_json.py <bq_query_output.json> <output_data.json>
"""
import json
import sys
from datetime import datetime, timezone


SOURCES = ["web_puro", "help_to_sell", "ayuda_venta"]
SEGMENT_STAGES = [
    "direccion", "zona", "datos_inmueble", "contacto",
    "caracteristicas", "ultimos_detalles", "felicitaciones",
]
ALL_STAGES = SEGMENT_STAGES + ["lead_hubspot"]
LOOKBACK_DAYS = 180


def main():
    if len(sys.argv) != 3:
        print("Usage: funnel_fuentes_to_json.py <bq_input.json> <data_output.json>",
              file=sys.stderr)
        sys.exit(1)

    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Pivot: (date, source) -> {stage: n, ...}
    pivot = {}
    completions_no_deal = {}
    dates_seen = set()
    sources_seen = set()
    for r in raw:
        d = r["d"]
        s = r["source"]
        stage = r["stage"]
        n = int(r["n"])
        dates_seen.add(d)
        sources_seen.add(s)
        if stage == "completions_no_deal":
            completions_no_deal[(d, s)] = n
        else:
            pivot.setdefault((d, s), {})[stage] = n

    # Ensure all (date, source) combinations exist with proper null/0 semantics.
    daily = []
    for d in sorted(dates_seen, reverse=True):
        for s in SOURCES:
            stages_dict = pivot.get((d, s), {})
            if s == "ayuda_venta":
                # Stages 1-7 quedan null (sin tracking); solo lead_hubspot tiene dato.
                entry_stages = {st: None for st in SEGMENT_STAGES}
                entry_stages["lead_hubspot"] = stages_dict.get("lead_hubspot", 0)
                entry_no_deal = None
            else:
                # Web puro y help-to-sell: completar con 0 los stages faltantes.
                entry_stages = {st: stages_dict.get(st, 0) for st in ALL_STAGES}
                entry_no_deal = completions_no_deal.get((d, s), 0)
            daily.append({
                "date": d,
                "source": s,
                "stages": entry_stages,
                "completions_no_deal": entry_no_deal,
            })

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tz": "America/Bogota",
        "lookback_days": LOOKBACK_DAYS,
        "daily": daily,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Wrote {len(daily)} daily entries to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Hacer ejecutable**

```bash
chmod +x scripts/funnel_fuentes_to_json.py
```

- [ ] **Step 3: Generar data.json local desde BQ y validar**

```bash
cd ~/habi/tableros-marketing
bq query --use_legacy_sql=false --format=json --max_rows=100000 \
  < funnel-fuentes/query.sql > /tmp/funnel-fuentes-raw.json
python3 scripts/funnel_fuentes_to_json.py \
  /tmp/funnel-fuentes-raw.json \
  funnel-fuentes/data.json
```

Expected stdout: `Wrote N daily entries to funnel-fuentes/data.json` con N entre 300 y 600 (180 días × 3 sources, menos días sin actividad).

- [ ] **Step 4: Validar shape del JSON**

```bash
python3 -c "
import json
d = json.load(open('funnel-fuentes/data.json'))
assert 'daily' in d, 'missing daily key'
assert d['tz'] == 'America/Bogota'
assert d['lookback_days'] == 180
sample = d['daily'][0]
assert set(sample.keys()) == {'date', 'source', 'stages', 'completions_no_deal'}
assert sample['source'] in ('web_puro', 'help_to_sell', 'ayuda_venta')
ayuda = [r for r in d['daily'] if r['source'] == 'ayuda_venta'][0]
assert ayuda['stages']['direccion'] is None, 'ayuda_venta direccion should be null'
assert ayuda['completions_no_deal'] is None
web = [r for r in d['daily'] if r['source'] == 'web_puro'][0]
assert isinstance(web['stages']['direccion'], int)
print('Shape OK -', len(d['daily']), 'entries')
"
```

Expected: `Shape OK - <N> entries`.

- [ ] **Step 5: Commit**

```bash
git add scripts/funnel_fuentes_to_json.py funnel-fuentes/data.json
git commit -m "Add funnel_fuentes_to_json transformer + initial data.json"
```

---

## Task 7: Frontend — esqueleto HTML, styles, header y back-link

**Files:**
- Modify: `funnel-fuentes/index.html`

**Goal:** crear el HTML base siguiendo las convenciones del hub (favicon megáfono, back-link, tema oscuro).

- [ ] **Step 1: Escribir el HTML base completo**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📢</text></svg>">
  <title>Funnel por fuente de lead</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      padding: 24px;
      line-height: 1.5;
    }
    .back-link {
      display: inline-block;
      color: #94a3b8;
      text-decoration: none;
      margin-bottom: 16px;
      font-size: 13px;
    }
    .back-link:hover { color: #f8fafc; }
    h1 { font-size: 24px; margin-bottom: 4px; }
    .subtitle { color: #94a3b8; font-size: 14px; margin-bottom: 24px; }
    .controls {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 24px;
      padding: 16px;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 8px;
    }
    .control-group { display: flex; gap: 6px; align-items: center; }
    .control-group label { font-size: 12px; color: #94a3b8; margin-right: 4px; }
    button.toggle {
      background: #334155; color: #e2e8f0; border: 1px solid #475569;
      padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 13px;
    }
    button.toggle.active { background: #818cf8; color: #0f172a; border-color: #818cf8; }
    button.toggle:hover:not(.active) { background: #475569; }
    .main { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 24px; }
    .footer-meta { color: #64748b; font-size: 11px; margin-top: 16px; text-align: right; }
  </style>
</head>
<body>
  <a href="../" class="back-link">← Volver (Tableros Marketing Sellers)</a>
  <h1>Funnel por fuente de lead</h1>
  <p class="subtitle">Web habi.co · Help-to-sell · Ayuda Venta (Inmo) — etapas y conversión a HubSpot</p>

  <div class="controls">
    <div class="control-group">
      <label>Vista:</label>
      <button class="toggle active" data-view="funnel">Funnel</button>
      <button class="toggle" data-view="tendencia">Tendencia</button>
    </div>
    <div class="control-group">
      <label>Ventana:</label>
      <button class="toggle" data-window="7">7d</button>
      <button class="toggle active" data-window="30">30d</button>
      <button class="toggle" data-window="90">90d</button>
    </div>
    <div class="control-group" id="granularity-group" style="display:none">
      <label>Granularidad:</label>
      <button class="toggle" data-granularity="D">Día</button>
      <button class="toggle active" data-granularity="W">Semana</button>
      <button class="toggle" data-granularity="M">Mes</button>
    </div>
  </div>

  <div class="main" id="main"></div>
  <p class="footer-meta" id="footer-meta"></p>

  <script>
    // TODO: implementar en próximos steps
    console.log("funnel-fuentes — frontend pendiente");
  </script>
</body>
</html>
```

- [ ] **Step 2: Abrir en navegador para sanity check del layout**

```bash
cd ~/habi/tableros-marketing
python3 -m http.server 8765 &
echo "Abre http://localhost:8765/funnel-fuentes/"
```

Verificar: se ve el header, los controles, el fondo oscuro, el back-link. Sin contenido en `.main` aún (es esperado).

- [ ] **Step 3: Matar el servidor cuando termines (Ctrl+C o `kill %1`).**

- [ ] **Step 4: Commit**

```bash
git add funnel-fuentes/index.html
git commit -m "Add funnel-fuentes index.html skeleton (header + controls + dark theme)"
```

---

## Task 8: Frontend — lógica de carga de data y agregación en JS

**Files:**
- Modify: `funnel-fuentes/index.html` (reemplazar `<script>` final)

**Goal:** cargar `data.json`, agregar por ventana, exponer estado global para las dos vistas.

- [ ] **Step 1: Reemplazar el `<script>` placeholder con lógica de carga**

```html
<script>
  const STAGES = [
    {id: 'direccion',        label: 'Dirección'},
    {id: 'zona',             label: 'Zona / Ubicación'},
    {id: 'datos_inmueble',   label: 'Datos inmueble'},
    {id: 'contacto',         label: 'Contacto'},
    {id: 'caracteristicas',  label: 'Características'},
    {id: 'ultimos_detalles', label: 'Últimos detalles'},
    {id: 'felicitaciones',   label: 'Felicitaciones (form completado)'},
    {id: 'lead_hubspot',     label: 'Lead en HubSpot'},
  ];
  const SOURCES = [
    {id: 'web_puro',     label: 'Web habi.co',     color: '#60a5fa'},
    {id: 'help_to_sell', label: 'Help-to-sell',    color: '#fb923c'},
    {id: 'ayuda_venta',  label: 'Ayuda Venta (Inmo)', color: '#34d399'},
  ];

  const state = {
    raw: null,
    view: 'funnel',
    windowDays: 30,
    granularity: 'W',
  };

  async function load() {
    const r = await fetch('./data.json', {cache: 'no-cache'});
    state.raw = await r.json();
    document.getElementById('footer-meta').textContent =
      `Generado ${state.raw.generated_at} · ventana lookback ${state.raw.lookback_days}d · TZ ${state.raw.tz}`;
    render();
  }

  function rowsInWindow() {
    const today = new Date(); today.setHours(0,0,0,0);
    const cutoff = new Date(today); cutoff.setDate(cutoff.getDate() - state.windowDays);
    const cutoffStr = cutoff.toISOString().slice(0,10);
    return state.raw.daily.filter(r => r.date >= cutoffStr);
  }

  function aggregateFunnel() {
    // Devuelve {source: {stage: total, ...}, completions_no_deal: {source: total}}
    const rows = rowsInWindow();
    const out = {}; const noDeal = {};
    for (const s of SOURCES) {
      out[s.id] = {};
      for (const st of STAGES) out[s.id][st.id] = 0;
      noDeal[s.id] = 0;
    }
    let allNull = {ayuda_venta: true};
    for (const r of rows) {
      for (const st of STAGES) {
        const v = r.stages[st.id];
        if (v === null) continue;
        out[r.source][st.id] += v;
        if (r.source === 'ayuda_venta' && v !== null) allNull.ayuda_venta = false;
      }
      if (r.completions_no_deal !== null) noDeal[r.source] += (r.completions_no_deal || 0);
    }
    // Si ayuda_venta nunca tuvo data en los stages 1-7, marcar como null para diferenciar de 0.
    if (allNull.ayuda_venta) {
      for (const st of STAGES) {
        if (st.id !== 'lead_hubspot') out.ayuda_venta[st.id] = null;
      }
    }
    return {totals: out, completionsNoDeal: noDeal};
  }

  function render() {
    if (!state.raw) return;
    document.getElementById('granularity-group').style.display =
      state.view === 'tendencia' ? 'flex' : 'none';
    if (state.view === 'funnel') renderFunnel();
    else renderTendencia();
  }

  function renderFunnel() {
    const main = document.getElementById('main');
    main.innerHTML = '<p style="color:#94a3b8">(funnel placeholder — Task 9)</p>';
  }

  function renderTendencia() {
    const main = document.getElementById('main');
    main.innerHTML = '<p style="color:#94a3b8">(tendencia placeholder — Task 10)</p>';
  }

  // Wire up controls
  document.querySelectorAll('button.toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.view !== undefined) {
        document.querySelectorAll('[data-view]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.view = btn.dataset.view;
      } else if (btn.dataset.window !== undefined) {
        document.querySelectorAll('[data-window]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.windowDays = parseInt(btn.dataset.window, 10);
      } else if (btn.dataset.granularity !== undefined) {
        document.querySelectorAll('[data-granularity]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.granularity = btn.dataset.granularity;
      }
      render();
    });
  });

  load();
</script>
```

- [ ] **Step 2: Sanity check en browser**

```bash
cd ~/habi/tableros-marketing && python3 -m http.server 8765 &
```

Abrir `http://localhost:8765/funnel-fuentes/` y verificar:
- En consola del browser no hay errores.
- Footer muestra `Generado ... · ventana lookback 180d · TZ America/Bogota`.
- Los toggles cambian de color al click.
- Cambiar a Tendencia muestra el control de Granularidad; Funnel lo oculta.

- [ ] **Step 3: Matar server.**

- [ ] **Step 4: Commit**

```bash
git add funnel-fuentes/index.html
git commit -m "Wire data.json loading + window/view state for funnel-fuentes"
```

---

## Task 9: Frontend — Vista Funnel (tabla 3×8 con heatmap)

**Files:**
- Modify: `funnel-fuentes/index.html` (reemplazar `renderFunnel()` y agregar CSS de tabla)

**Goal:** renderizar tabla con 3 columnas (fuentes) × 8 filas (etapas), cada celda con count + % step→step, heatmap por fila.

- [ ] **Step 1: Agregar estilos de tabla al `<style>`**

```css
/* Agregar dentro del <style> existente */
table.funnel { width: 100%; border-collapse: collapse; }
table.funnel th, table.funnel td {
  padding: 12px 16px; text-align: right; border-bottom: 1px solid #334155;
  font-variant-numeric: tabular-nums;
}
table.funnel th { font-size: 12px; color: #94a3b8; font-weight: 600; }
table.funnel th.stage-col, table.funnel td.stage-col { text-align: left; }
table.funnel td .count { font-size: 18px; font-weight: 600; }
table.funnel td .step-pct { font-size: 11px; color: #94a3b8; margin-top: 2px; }
table.funnel td.no-data { color: #64748b; font-style: italic; }
table.funnel tr:hover td { background: #273449; }
.no-deal-chip {
  display: inline-block; margin-top: 4px; padding: 2px 6px;
  background: #475569; border-radius: 4px; font-size: 10px; color: #cbd5e1;
}
.source-pill {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;
}
```

- [ ] **Step 2: Implementar `renderFunnel()`**

Reemplazar la función placeholder por:

```javascript
function renderFunnel() {
  const {totals, completionsNoDeal} = aggregateFunnel();

  // Calcular % step→step por fuente (skipping null values).
  const stepPct = {};
  for (const s of SOURCES) {
    stepPct[s.id] = {};
    let prev = null;
    for (const st of STAGES) {
      const v = totals[s.id][st.id];
      if (v === null) { stepPct[s.id][st.id] = null; prev = null; continue; }
      if (prev === null || prev === 0) { stepPct[s.id][st.id] = null; }
      else { stepPct[s.id][st.id] = v / prev; }
      prev = v;
    }
  }

  // Heatmap por fila: color basado en % step→step relativo entre las 3 fuentes.
  function heatColor(pct) {
    if (pct === null || pct === undefined) return 'transparent';
    // 0% rojo → 100% verde, vía amarillo.
    const r = Math.round(255 * (1 - pct));
    const g = Math.round(180 * pct);
    return `rgba(${r}, ${g}, 80, 0.15)`;
  }

  let html = '<table class="funnel"><thead><tr><th class="stage-col">Etapa</th>';
  for (const s of SOURCES) {
    html += `<th><span class="source-pill" style="background:${s.color}"></span>${s.label}</th>`;
  }
  html += '</tr></thead><tbody>';

  for (let i = 0; i < STAGES.length; i++) {
    const st = STAGES[i];
    html += `<tr><td class="stage-col">${st.label}</td>`;
    for (const s of SOURCES) {
      const v = totals[s.id][st.id];
      const pct = stepPct[s.id][st.id];
      if (v === null) {
        html += `<td class="no-data" title="Sin tracking — pixel solo en habi.co">—</td>`;
      } else {
        const pctStr = pct === null ? '' : ` <span class="step-pct">${(pct*100).toFixed(0)}% ↓</span>`;
        const bg = heatColor(pct);
        html += `<td style="background:${bg}"><div class="count">${v.toLocaleString('es-CO')}</div>${pctStr}`;
        if (st.id === 'lead_hubspot' && completionsNoDeal[s.id] > 0) {
          html += `<div class="no-deal-chip" title="Form completado pero sin deal vinculado en ventana">${completionsNoDeal[s.id]} sin deal</div>`;
        }
        html += '</td>';
      }
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  document.getElementById('main').innerHTML = html;
}
```

- [ ] **Step 3: Sanity check en browser**

```bash
cd ~/habi/tableros-marketing && python3 -m http.server 8765 &
```

Abrir `http://localhost:8765/funnel-fuentes/` y verificar:
- Tabla 3×8 visible.
- `web_puro` con números altos en `Dirección` (miles), decrecientes hacia `Lead en HubSpot`.
- `ayuda_venta` con `—` en filas 1-7 y count chiquito en `Lead en HubSpot`.
- Heatmap visible en celdas (colores suaves).
- Hover sobre `—` muestra el tooltip.
- Cambiar ventana (7d/30d/90d) actualiza los números.

- [ ] **Step 4: Matar server. Commit.**

```bash
git add funnel-fuentes/index.html
git commit -m "Render funnel view: 3-source table with step-to-step conversion + heatmap"
```

---

## Task 10: Frontend — Vista Tendencia (Chart.js)

**Files:**
- Modify: `funnel-fuentes/index.html` (reemplazar `renderTendencia()`)

**Goal:** gráfico de líneas con 3 series (una por fuente), métrica = Leads en HubSpot por período según granularidad.

- [ ] **Step 1: Agregar CSS para el chart container**

```css
/* Agregar al <style> */
.chart-container { position: relative; height: 380px; margin-bottom: 24px; }
table.summary { width: 100%; border-collapse: collapse; font-size: 13px; }
table.summary th, table.summary td {
  padding: 8px 12px; text-align: right; border-bottom: 1px solid #334155;
}
table.summary th { color: #94a3b8; font-weight: 600; font-size: 11px; }
table.summary td:first-child, table.summary th:first-child { text-align: left; }
```

- [ ] **Step 2: Implementar funciones de agregación temporal y render**

Reemplazar `renderTendencia()` por:

```javascript
function bucketDate(dateStr, granularity) {
  const d = new Date(dateStr + 'T00:00:00');
  if (granularity === 'D') return dateStr;
  if (granularity === 'W') {
    // ISO week starts Monday. Get Monday of this week.
    const day = d.getDay() === 0 ? 7 : d.getDay();
    d.setDate(d.getDate() - (day - 1));
    return d.toISOString().slice(0,10);
  }
  if (granularity === 'M') return dateStr.slice(0, 7) + '-01';
  return dateStr;
}

function aggregateTendencia() {
  const rows = rowsInWindow();
  const buckets = new Map(); // key: bucket date, value: {source: leads_total}
  for (const r of rows) {
    const b = bucketDate(r.date, state.granularity);
    if (!buckets.has(b)) {
      const init = {};
      for (const s of SOURCES) init[s.id] = 0;
      buckets.set(b, init);
    }
    const v = r.stages.lead_hubspot;
    if (v !== null && v !== undefined) buckets.get(b)[r.source] += v;
  }
  const sortedKeys = [...buckets.keys()].sort();
  return {labels: sortedKeys, data: sortedKeys.map(k => buckets.get(k))};
}

let chartInstance = null;
function renderTendencia() {
  const {labels, data} = aggregateTendencia();
  const main = document.getElementById('main');
  main.innerHTML = `
    <div class="chart-container"><canvas id="trend-chart"></canvas></div>
    <table class="summary" id="summary-table"></table>
  `;

  const datasets = SOURCES.map(s => ({
    label: s.label,
    data: data.map(d => d[s.id]),
    borderColor: s.color,
    backgroundColor: s.color + '33',
    tension: 0.3,
    fill: false,
  }));

  if (chartInstance) chartInstance.destroy();
  chartInstance = new Chart(document.getElementById('trend-chart'), {
    type: 'line',
    data: {labels, datasets},
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: {labels: {color: '#e2e8f0'}},
        tooltip: {mode: 'index', intersect: false},
      },
      scales: {
        x: {ticks: {color: '#94a3b8'}, grid: {color: '#334155'}},
        y: {ticks: {color: '#94a3b8'}, grid: {color: '#334155'}, beginAtZero: true,
            title: {display: true, text: 'Leads creados', color: '#94a3b8'}},
      },
    },
  });

  // Summary table
  let sumHtml = '<thead><tr><th>Fuente</th><th>Leads totales</th><th>Promedio/período</th><th>Mejor período</th></tr></thead><tbody>';
  for (const s of SOURCES) {
    const series = data.map(d => d[s.id]);
    const total = series.reduce((a,b) => a+b, 0);
    const avg = series.length ? total/series.length : 0;
    let bestVal = 0, bestIdx = -1;
    series.forEach((v, i) => { if (v > bestVal) { bestVal = v; bestIdx = i; } });
    const bestLabel = bestIdx >= 0 ? `${labels[bestIdx]} (${bestVal})` : '—';
    sumHtml += `<tr><td><span class="source-pill" style="background:${s.color}"></span>${s.label}</td>` +
               `<td>${total.toLocaleString('es-CO')}</td>` +
               `<td>${avg.toFixed(1)}</td>` +
               `<td>${bestLabel}</td></tr>`;
  }
  sumHtml += '</tbody>';
  document.getElementById('summary-table').innerHTML = sumHtml;
}
```

- [ ] **Step 3: Sanity check**

```bash
cd ~/habi/tableros-marketing && python3 -m http.server 8765 &
```

Abrir `http://localhost:8765/funnel-fuentes/` → click `Tendencia`:
- Aparece chart con 3 líneas.
- Granularidad toggle visible y cambia el chart.
- Tabla resumen abajo del chart con totales por fuente.
- Cambiar ventana 7d/30d/90d actualiza chart y tabla.

- [ ] **Step 4: Commit**

```bash
git add funnel-fuentes/index.html
git commit -m "Render tendencia view: Chart.js line chart + summary table per source"
```

---

## Task 11: Agregar landing card al `index.html` del root

**Files:**
- Modify: `index.html` (root)

- [ ] **Step 1: Leer el index.html del root para identificar donde van las cards**

```bash
cat ~/habi/tableros-marketing/index.html | head -60
```

- [ ] **Step 2: Agregar la nueva card en la sección de cards existente**

(Localizar el bloque de `<a class="card">…</a>` y agregar uno nuevo al final, antes de cerrar el contenedor.)

```html
<a class="card" href="./funnel-fuentes/">
  <h3>Funnel por fuente de lead</h3>
  <p>Web habi.co · Help-to-sell · Ayuda Venta (Inmo) — etapas y conversión a HubSpot</p>
</a>
```

- [ ] **Step 3: Sanity check en browser**

```bash
cd ~/habi/tableros-marketing && python3 -m http.server 8765 &
```

Abrir `http://localhost:8765/` y verificar que la nueva card aparece en el grid de tableros.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "Add funnel-fuentes card to landing"
```

---

## Task 12: Integración al workflow consolidado (`update-data.yml`)

**Files:**
- Modify: `.github/workflows/update-data.yml`

**Goal:** que el cron diario regenere `funnel-fuentes/data.json`.

- [ ] **Step 1: Leer el workflow actual para ubicar dónde insertar el nuevo step**

```bash
cat ~/habi/tableros-marketing/.github/workflows/update-data.yml
```

Identificar dónde están los steps de otros tableros (probablemente con nombres tipo `Query <tablero>` y `Build <tablero> data`). Insertar antes del step de commit final.

- [ ] **Step 2: Agregar los steps de funnel-fuentes**

```yaml
- name: Funnel fuentes - query BigQuery
  if: always()
  run: |
    bq query --use_legacy_sql=false --format=json --max_rows=100000 \
      < funnel-fuentes/query.sql > /tmp/funnel-fuentes-raw.json

- name: Funnel fuentes - build data.json
  if: always()
  run: |
    python3 scripts/funnel_fuentes_to_json.py \
      /tmp/funnel-fuentes-raw.json \
      funnel-fuentes/data.json
```

- [ ] **Step 3: Verificar que el step de commit final ya hace `git add -A` o agregar explícitamente el archivo**

Si el commit usa rutas explícitas, agregar `funnel-fuentes/data.json` a la lista. Si usa `git add -A` o `git add .`, no hay que tocar.

- [ ] **Step 4: Commit del workflow**

```bash
git add .github/workflows/update-data.yml
git commit -m "Wire funnel-fuentes into update-data workflow"
```

- [ ] **Step 5: Push de toda la rama y disparar el workflow manualmente para verificar**

```bash
git push origin main
gh workflow run update-data.yml
gh run watch
```

Expected: workflow exitoso, commit automático con `funnel-fuentes/data.json` actualizado. Abrir la URL de GH Pages https://camilootoya-habi.github.io/tableros-marketing-habi/funnel-fuentes/ y verificar que el tablero levanta y muestra datos.

---

## Task 13: Documentar follow-ups en memoria

**Files:**
- Create: `~/.claude/projects/-home-administrador/memory/habi/tableros/funnel_fuentes.md`
- Modify: `~/.claude/projects/-home-administrador/memory/MEMORY.md`

**Goal:** dejar registro persistente para futuras sesiones.

- [ ] **Step 1: Crear el archivo de memoria del tablero**

```markdown
---
name: Tablero Funnel por fuente de lead
description: Sub-tablero CO comparando funnel de Web habi.co vs Help-to-sell vs Ayuda Venta (Inmo) - etapas Segment + atribución a HubSpot vía chain UUID
metadata:
  type: project
---

## URL y paths
- Live: https://camilootoya-habi.github.io/tableros-marketing-habi/funnel-fuentes/
- Local: `~/habi/tableros-marketing/funnel-fuentes/`
- Spec: `docs/superpowers/specs/2026-05-12-funnel-fuentes-design.md`

## Qué muestra
- Vista Funnel: 3 fuentes × 8 etapas (`/direccion` → `/felicitaciones` + Lead en HubSpot).
- Vista Tendencia: leads creados/período por fuente (Chart.js).
- Ventana 7d/30d/90d, granularidad D/W/M.

## Atribución a HubSpot (clave del proyecto)
Chain UUID: `anonymous_id → select_content.backbone_uuid → web_global_api_business.uuid (= backbone_uuid) → .deal_uuid → habi_db_tabla_negocio_inmueble.uuid → .nid → tabla_inmuebles_general.fecha_creacion`.

Match estricto día Bogotá entre `/felicitaciones` event y `fecha_creacion` del deal.

- **Ayuda Venta** (form Inmo en vercel): no pasa por este chain (b.uuid = NULL). Se cuenta directo desde `hubspot.deals.sub_fuente = 'Ayuda Venta'`.

## Follow-ups pendientes
- Investigar el gap `completions_no_deal` (chip al lado de fila 8) — posible leakage de leads no atribuidos.
- Considerar pixel Segment en `ayudaventas-habi-web.vercel.app` para destapar etapas de Ayuda Venta.
- Routing del form "Inmo" en vercel a pipeline real de Inmo (hoy `aplica_para_inmobiliaria = NULL`).
```

- [ ] **Step 2: Agregar entrada al MEMORY.md**

En la sección "Tableros Marketing", agregar:

```markdown
- [Funnel por fuente de lead](habi/tableros/funnel_fuentes.md) — CO, 3 fuentes (Web/Help-to-sell/Ayuda Venta), atribución vía chain UUID, gap a investigar
```

- [ ] **Step 3: Verificar (no commit — memoria es local, no se commitea al repo de tableros).**

---

## Self-review (post-plan)

Coverage del spec:
- §2 Fuentes → Task 2 (clasificación en CTE pages_classified)
- §3 Etapas → Task 3 (stages_daily) + Task 9 (render)
- §4 Atribución UUID → Task 4 (uuid_chain + leads_ab_daily) + Task 5 (leads_c_daily)
- §5 Vista Tendencia → Task 10
- §6 Controles UI → Task 7 (skeleton) + Task 8 (wiring)
- §7 JSON shape + SQL → Tasks 2-6
- §8 Workflow → Task 12
- §9 Landing card → Task 11
- §10 Frontend completo → Tasks 7-10
- §11 Follow-ups → Task 13 (memoria)
- §12 Validación → Tasks 4, 5 (sanity con NIDs conocidos)

Sin TBDs ni placeholders.
Type/naming consistency: `web_puro`/`help_to_sell`/`ayuda_venta` consistentes en SQL, Python y JS.
Granularidad de tasks: 13 tasks con ~3-5 steps cada uno, suma ~50 steps de 2-5 min ≈ 2-3 hrs de implementación neta.
