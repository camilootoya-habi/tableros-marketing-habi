# Funnel Web MX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new dashboard at `funnel-web-mx/` that shows the 13-stage click→register funnel for MX WEB source, with cluster breakdowns by canal/plataforma, device, and zona del inmueble — using Segment.pages data to validate platform-reported clicks.

**Architecture:** Static HTML dashboard hosted on GitHub Pages, fed by a `data.json` that's auto-updated every 4h via GitHub Actions running 4 BigQuery queries + a Python merge script. Same pattern as the existing `wbr-2-0` tableró.

**Tech Stack:** BigQuery SQL, Python 3 stdlib only, vanilla HTML/CSS/JS (no build step), GitHub Actions.

**Spec reference:** `docs/superpowers/specs/2026-05-25-funnel-web-mx-design.md`

---

## Phase 0 — Pre-implementation validations

These tasks verify assumptions in the spec before writing any production code. Each one is a short read-only BQ check; do NOT skip them — wrong assumptions here cause rework downstream.

### Task 0.1: Verify partition of `mx_segment_profiles.pages`

**Files:** none (read-only checks)

- [ ] **Step 1: Check partitioning metadata**

Run:
```bash
bq show --format=prettyjson sellers-main-prod:mx_segment_profiles.pages | python3 -c "import json,sys; d=json.load(sys.stdin); print('partitioning:', d.get('timePartitioning')); print('clustering:', d.get('clustering'))"
```

Expected: `timePartitioning` field is non-null and references a date/timestamp column (typically `timestamp` or `_PARTITIONTIME`). Record the partition column name.

- [ ] **Step 2: Estimate scan size for one week's filter**

Run:
```bash
bq query --use_legacy_sql=false --dry_run --format=prettyjson "SELECT 1 FROM \`sellers-main-prod.mx_segment_profiles.pages\` WHERE DATE(timestamp, 'America/Mexico_City') >= '2026-05-18' AND DATE(timestamp, 'America/Mexico_City') < '2026-05-25'" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'GB scanned: {int(d[\"statistics\"][\"totalBytesProcessed\"])/1e9:.2f}')"
```

Expected: under 1 GB for one week. If it scans >5 GB, the table isn't using partition pruning effectively. In that case, document the issue and adjust the Phase 2 query to use the actual partition column.

- [ ] **Step 3: Estimate scan size for 140-day window**

Run:
```bash
bq query --use_legacy_sql=false --dry_run --format=prettyjson "SELECT 1 FROM \`sellers-main-prod.mx_segment_profiles.pages\` WHERE DATE(timestamp, 'America/Mexico_City') >= DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY)" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'GB scanned: {int(d[\"statistics\"][\"totalBytesProcessed\"])/1e9:.2f}')"
```

Expected: under 30 GB per full window run. If higher, flag in plan checkpoint before continuing.

### Task 0.2: Verify `web_global_api_business.data` JSON contains zone info

**Files:** none (read-only)

- [ ] **Step 1: Sample a recent MX row and inspect the JSON keys**

Run:
```bash
bq query --use_legacy_sql=false --format=prettyjson --max_rows=3 "SELECT uuid, deal_uuid, status, JSON_KEYS(data) AS keys, SUBSTR(TO_JSON_STRING(data), 1, 600) AS sample FROM \`sellers-main-prod.top_funnel.web_global_api_business\` WHERE country='MX' AND deal_uuid != '0' AND created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) ORDER BY created_at DESC LIMIT 3"
```

Expected: see keys like `ciudad`, `zona_mediana_id`, `localizacion`, or similar. Record the EXACT keys that contain city/zone info.

- [ ] **Step 2: Decision gate**

If zone info IS present in `data`: proceed normally. The Phase 2 `query_backbone.sql` will extract zona via `JSON_EXTRACT_SCALAR(data, '$.<key>')`.

If zone info is NOT present in `data`: simplify the spec — zone is only known at lead stage (etapa 13). Update `query_backbone.sql` to NOT attempt zone attribution for intermediate form steps, and note this limitation in the implementation. Notify the user before continuing.

### Task 0.3: Verify select_content chain coverage

**Files:** none (read-only)

- [ ] **Step 1: Measure % of backbone sessions with select_content chain**

Run:
```bash
bq query --use_legacy_sql=false --format=prettyjson "WITH b AS (SELECT uuid FROM \`sellers-main-prod.top_funnel.web_global_api_business\` WHERE country='MX' AND DATE(created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)), sc AS (SELECT DISTINCT backbone_uuid FROM \`sellers-main-prod.mx_segment_profiles.select_content\` WHERE DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) AND backbone_uuid IS NOT NULL) SELECT COUNT(*) AS total_backbones, COUNT(sc.backbone_uuid) AS with_chain, ROUND(COUNT(sc.backbone_uuid) / COUNT(*) * 100, 1) AS pct FROM b LEFT JOIN sc ON sc.backbone_uuid = b.uuid"
```

Expected: pct > 70%. Record the actual value.

- [ ] **Step 2: Decision gate**

If pct >= 50%: proceed. Document the pct in implementation notes — visitors without chain will be categorized as `Direct/Direct` + `Unknown` device.

If pct < 50%: the attribution will be too poor. Stop and ask user how to proceed (could use a different join key, or accept the limitation more aggressively).

### Task 0.4: Verify `canal_adquisicion='Web'` covers WEB spend

**Files:** none (read-only)

- [ ] **Step 1: List distinct canal_adquisicion values with spend totals (last 30d)**

Run:
```bash
bq query --use_legacy_sql=false --format=prettyjson "SELECT canal_adquisicion, COUNT(*) AS rows, ROUND(SUM(spend), 0) AS total_spend, ROUND(SUM(clicks), 0) AS total_clicks FROM \`papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx\` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) GROUP BY 1 ORDER BY total_spend DESC"
```

Expected: see `Web`, `Habimetro`, `Lead Form`, and possibly `Calculadora de gastos`, etc. Confirm `Web` is the right label for WEB Paid spend.

- [ ] **Step 2: Confirm plataforma values are clean**

Run:
```bash
bq query --use_legacy_sql=false --format=prettyjson "SELECT plataforma, ROUND(SUM(spend), 0) AS total_spend FROM \`papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx\` WHERE canal_adquisicion='Web' AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) GROUP BY 1 ORDER BY total_spend DESC LIMIT 20"
```

Expected: see Google, Facebook/Meta, Bing, TikTok, and possibly DV360, Outbrain, etc. Record the exact platform labels to ensure the CASE statement in `query_clicks.sql` maps them correctly.

### Task 0.5: Commit Phase 0 findings as notes

**Files:** Create `docs/superpowers/notes/2026-05-25-funnel-web-mx-validations.md`

- [ ] **Step 1: Write the notes file** with the recorded values from tasks 0.1–0.4:

```markdown
# Funnel Web MX — Validations (Phase 0)

Date: 2026-05-25

## 0.1 segment.pages partitioning
- Partition column: [from Task 0.1 Step 1]
- 1-week scan: [GB from Task 0.1 Step 2]
- 140-day scan: [GB from Task 0.1 Step 3]

## 0.2 web_global_api_business.data zone keys
- Keys found: [list from Task 0.2]
- Decision: [zone available in intermediate steps / only at lead stage]

## 0.3 select_content chain coverage
- pct with chain: [from Task 0.3]
- Decision: [proceed / escalated]

## 0.4 canal_adquisicion + plataforma values
- canal_adquisicion='Web' total spend last 30d: [value]
- Plataforma labels seen: [list with totals]
- CASE statement adjustments needed: [yes/no, details]
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/notes/2026-05-25-funnel-web-mx-validations.md
git commit -m "notes: Phase 0 validations for funnel-web-mx"
```

---

## Phase 1 — Scaffolding

### Task 1.1: Create folder structure

**Files:**
- Create: `funnel-web-mx/` directory and placeholder files

- [ ] **Step 1: Create the directory and placeholder files**

```bash
mkdir -p funnel-web-mx
cd funnel-web-mx
touch query_clicks.sql query_sessions.sql query_backbone.sql query_leads.sql build_data.py index.html
echo '{}' > data.json
cd ..
```

- [ ] **Step 2: Verify**

Run:
```bash
ls -la funnel-web-mx/
```

Expected: 7 files listed (6 source + data.json).

- [ ] **Step 3: Commit scaffolding**

```bash
git add funnel-web-mx/
git commit -m "scaffold: funnel-web-mx folder + placeholders"
```

---

## Phase 2 — SQL queries

For each SQL task: write the file, dry-run it (verifies syntax + scan size), then execute it, then inspect a sample row. Treat the "dry-run scan size under X GB" as the test that gates correctness.

### Task 2.1: Write `query_clicks.sql`

**Files:**
- Create: `funnel-web-mx/query_clicks.sql`

- [ ] **Step 1: Write the SQL**

Write to `funnel-web-mx/query_clicks.sql`:

```sql
-- Funnel Web MX — Clicks reportados (etapa 1 del funnel)
-- Source: papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx (canal_adquisicion='Web')
-- Output: one row per (week_start, plataforma) with spend / clicks / impressions

WITH base AS (
  SELECT
    DATE_TRUNC(date, ISOWEEK) AS week,
    CASE
      WHEN LOWER(plataforma) LIKE '%google%' THEN 'Google'
      WHEN LOWER(plataforma) IN ('facebook', 'instagram', 'meta', 'fb', 'ig') THEN 'Meta'
      WHEN LOWER(plataforma) LIKE '%bing%' THEN 'Bing'
      WHEN LOWER(plataforma) LIKE '%tiktok%' THEN 'TikTok'
      ELSE 'Otro'
    END AS plataforma_norm,
    spend,
    clicks,
    impressions
  FROM `papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx`
  WHERE canal_adquisicion = 'Web'
    AND date >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK)
    AND date < DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
)
SELECT
  CAST(week AS STRING) AS week_start,
  plataforma_norm AS plataforma,
  CAST(ROUND(SUM(spend), 0) AS INT64) AS spend,
  CAST(SUM(clicks) AS INT64) AS clicks,
  CAST(SUM(impressions) AS INT64) AS impressions
FROM base
GROUP BY 1, 2
ORDER BY 1, 2
```

- [ ] **Step 2: Dry-run for scan estimate**

Run:
```bash
bq query --use_legacy_sql=false --dry_run --format=prettyjson < funnel-web-mx/query_clicks.sql | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'GB scanned: {int(d[\"statistics\"][\"totalBytesProcessed\"])/1e9:.3f}')"
```

Expected: < 0.1 GB. If > 0.5 GB, the partition filter isn't working — inspect schema.

- [ ] **Step 3: Execute and inspect**

Run:
```bash
bq query --use_legacy_sql=false --format=prettyjson --max_rows=10 < funnel-web-mx/query_clicks.sql
```

Expected: rows with week_start in ISO format, plataforma in {Google, Meta, Bing, TikTok, Otro}, sensible spend/clicks values. Last week_start should match the most recent complete ISO week.

- [ ] **Step 4: Commit**

```bash
git add funnel-web-mx/query_clicks.sql
git commit -m "query: funnel-web-mx clicks (etapa 1)"
```

### Task 2.2: Write `query_sessions.sql`

**Files:**
- Create: `funnel-web-mx/query_sessions.sql`

- [ ] **Step 1: Write the SQL**

Write to `funnel-web-mx/query_sessions.sql`:

```sql
-- Funnel Web MX — Sesiones y form page steps (etapas 2-10, 12)
-- Source: sellers-main-prod.mx_segment_profiles.pages
-- Filter to habi.mx host, window of 140 days
-- Output: one row per (week_start, stage, canal_plat, device) with n_visitors

WITH evs AS (
  SELECT
    anonymous_id,
    DATE_TRUNC(DATE(timestamp, 'America/Mexico_City'), ISOWEEK) AS week,
    timestamp AS ts,
    context_page_path AS path,
    LOWER(IFNULL(context_campaign_utm_source, '')) AS utm_source,
    LOWER(IFNULL(context_campaign_utm_medium, '')) AS utm_medium,
    context_user_agent_data_mobile AS is_mobile,
    LOWER(IFNULL(context_user_agent_data_platform, '')) AS ua_platform
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Mexico_City') >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK)
    AND DATE(timestamp, 'America/Mexico_City') < DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
    AND context_page_url LIKE '%habi.mx%'
    AND anonymous_id IS NOT NULL
),
first_event AS (
  SELECT
    anonymous_id,
    week,
    ARRAY_AGG(STRUCT(utm_source, utm_medium, is_mobile, ua_platform) ORDER BY ts LIMIT 1)[OFFSET(0)] AS fe
  FROM evs
  GROUP BY 1, 2
),
attr AS (
  SELECT
    anonymous_id,
    week,
    CASE
      WHEN fe.utm_source LIKE '%google%' AND fe.utm_medium IN ('cpc', 'paid', 'ppc', 'paidsearch') THEN 'Google/Paid'
      WHEN fe.utm_source LIKE '%google%' THEN 'Google/Organic'
      WHEN fe.utm_source IN ('facebook', 'instagram', 'meta', 'fb', 'ig') AND fe.utm_medium IN ('cpc', 'paid', 'ppc', 'paid_social', 'paidsocial') THEN 'Meta/Paid'
      WHEN fe.utm_source IN ('facebook', 'instagram', 'meta', 'fb', 'ig') THEN 'Meta/Organic'
      WHEN fe.utm_source LIKE '%bing%' THEN 'Bing/Paid'
      WHEN fe.utm_source LIKE '%tiktok%' THEN 'TikTok/Paid'
      WHEN fe.utm_source = '' THEN 'Direct/Direct'
      ELSE 'Otro/Otro'
    END AS canal_plat,
    CASE
      WHEN fe.is_mobile = TRUE AND fe.ua_platform LIKE '%ipad%' THEN 'tablet'
      WHEN fe.is_mobile = TRUE THEN 'mobile'
      WHEN fe.is_mobile = FALSE THEN 'desktop'
      ELSE 'unknown'
    END AS device
  FROM first_event
),
visits AS (
  SELECT
    e.anonymous_id,
    e.week,
    e.path,
    a.canal_plat,
    a.device
  FROM evs e
  JOIN attr a USING (anonymous_id, week)
),
stage_visits AS (
  SELECT
    week,
    CASE path
      WHEN '/formulario-inmueble/inicio' THEN 'inicio'
      WHEN '/formulario-inmueble/inmuebles-zona' THEN 'zona'
      WHEN '/formulario-inmueble/confirmar-ubicacion-mx' THEN 'confirmar_ubicacion'
      WHEN '/formulario-inmueble/datos-inmueble' THEN 'datos_inmueble'
      WHEN '/formulario-inmueble/caracteristicas' THEN 'caracteristicas'
      WHEN '/formulario-inmueble/ultimos-detalles' THEN 'ultimos_detalles'
      WHEN '/formulario-inmueble/sugerencias-de-propiedades' THEN 'sugerencias'
      WHEN '/formulario-inmueble/editar-sugerencias' THEN 'sugerencias'
      WHEN '/formulario-inmueble/contacto' THEN 'contacto'
      WHEN '/formulario-inmueble/felicitaciones' THEN 'felicitaciones'
      ELSE NULL
    END AS stage,
    canal_plat,
    device,
    anonymous_id
  FROM visits
),
agg_stages AS (
  SELECT
    CAST(week AS STRING) AS week_start,
    stage,
    canal_plat,
    device,
    COUNT(DISTINCT anonymous_id) AS n_visitors
  FROM stage_visits
  WHERE stage IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
agg_session AS (
  SELECT
    CAST(week AS STRING) AS week_start,
    'session' AS stage,
    canal_plat,
    device,
    COUNT(DISTINCT anonymous_id) AS n_visitors
  FROM visits
  GROUP BY 1, 3, 4
)
SELECT * FROM agg_stages
UNION ALL
SELECT * FROM agg_session
ORDER BY week_start, stage, canal_plat, device
```

- [ ] **Step 2: Dry-run estimate**

Run:
```bash
bq query --use_legacy_sql=false --dry_run --format=prettyjson < funnel-web-mx/query_sessions.sql | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'GB scanned: {int(d[\"statistics\"][\"totalBytesProcessed\"])/1e9:.2f}')"
```

Expected: < 30 GB. If > 50 GB, check that the partition filter is using the correct column (might need `_PARTITIONTIME` or similar based on Task 0.1 findings).

- [ ] **Step 3: Execute on a 14-day window first (cheap sanity check)**

Run:
```bash
bq query --use_legacy_sql=false --format=prettyjson --max_rows=20 "$(sed 's/INTERVAL 140 DAY/INTERVAL 14 DAY/g' funnel-web-mx/query_sessions.sql)"
```

Expected: 20 sample rows. Verify:
- `stage` values include `session`, `inicio`, `zona`, `confirmar_ubicacion`, `datos_inmueble`, `caracteristicas`, `ultimos_detalles`, `sugerencias`, `contacto`, `felicitaciones`.
- `canal_plat` values are mostly `Direct/Direct`, `Google/Paid`, `Meta/Paid`, with some `Google/Organic`, `Meta/Organic`.
- `device` is `mobile`, `desktop`, or `tablet` (rarely `unknown`).
- `n_visitors` integers are positive and decreasing roughly through the funnel.

- [ ] **Step 4: Execute full 140-day window**

Run:
```bash
bq query --use_legacy_sql=false --format=prettyjson --max_rows=10000 < funnel-web-mx/query_sessions.sql > /tmp/sessions_sample.json
python3 -c "import json; d=json.load(open('/tmp/sessions_sample.json')); print(f'rows: {len(d)}'); weeks=sorted({r[\"week_start\"] for r in d}); print(f'weeks: {len(weeks)} ({weeks[0]} .. {weeks[-1]})')"
```

Expected: ~20 weeks of data, hundreds-to-thousands of rows total.

- [ ] **Step 5: Commit**

```bash
git add funnel-web-mx/query_sessions.sql
git commit -m "query: funnel-web-mx sessions + form steps (etapas 2-10,12)"
```

### Task 2.3: Write `query_backbone.sql`

**Files:**
- Create: `funnel-web-mx/query_backbone.sql`

The exact JSON extraction for zone depends on Task 0.2 findings. The template below assumes zone keys in `data` JSON. If Task 0.2 showed no zone in `data`, REMOVE the zone-extraction lines and set zona columns to NULL.

- [ ] **Step 1: Write the SQL**

Write to `funnel-web-mx/query_backbone.sql`:

```sql
-- Funnel Web MX — Form start + submit (etapa 11)
-- Source: sellers-main-prod.top_funnel.web_global_api_business (country='MX')
-- Joined with select_content + pages for UTM/device first-touch attribution
-- Output: one row per (week_start, stage, canal_plat, device, ciudad) with counts

WITH bb AS (
  SELECT
    uuid AS backbone_uuid,
    deal_uuid,
    DATE_TRUNC(DATE(created_at, 'America/Mexico_City'), ISOWEEK) AS week_start,
    JSON_EXTRACT_SCALAR(data, '$.location.city') AS ciudad_raw
    -- NOTE: If Task 0.2 found a different JSON path, replace '$.location.city' accordingly.
    -- If no zone info in JSON, replace the line above with: CAST(NULL AS STRING) AS ciudad_raw
  FROM `sellers-main-prod.top_funnel.web_global_api_business`
  WHERE country = 'MX'
    AND DATE(created_at, 'America/Mexico_City') >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK)
    AND DATE(created_at, 'America/Mexico_City') < DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
),
sc AS (
  SELECT
    backbone_uuid,
    ARRAY_AGG(STRUCT(anonymous_id, timestamp) ORDER BY timestamp LIMIT 1)[OFFSET(0)].anonymous_id AS anonymous_id
  FROM `sellers-main-prod.mx_segment_profiles.select_content`
  WHERE backbone_uuid IS NOT NULL
    AND DATE(timestamp, 'America/Mexico_City') >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 150 DAY), ISOWEEK)
  GROUP BY 1
),
first_pg AS (
  SELECT
    anonymous_id,
    DATE_TRUNC(DATE(timestamp, 'America/Mexico_City'), ISOWEEK) AS week,
    ARRAY_AGG(STRUCT(
      LOWER(IFNULL(context_campaign_utm_source, '')) AS utm_source,
      LOWER(IFNULL(context_campaign_utm_medium, '')) AS utm_medium,
      context_user_agent_data_mobile AS is_mobile,
      LOWER(IFNULL(context_user_agent_data_platform, '')) AS ua_platform
    ) ORDER BY timestamp LIMIT 1)[OFFSET(0)] AS fe
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Mexico_City') >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK)
    AND DATE(timestamp, 'America/Mexico_City') < DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
    AND context_page_url LIKE '%habi.mx%'
    AND anonymous_id IS NOT NULL
  GROUP BY 1, 2
),
enriched AS (
  SELECT
    bb.backbone_uuid,
    bb.deal_uuid,
    bb.week_start,
    bb.ciudad_raw,
    sc.anonymous_id,
    fp.fe.utm_source,
    fp.fe.utm_medium,
    fp.fe.is_mobile,
    fp.fe.ua_platform
  FROM bb
  LEFT JOIN sc ON sc.backbone_uuid = bb.backbone_uuid
  LEFT JOIN first_pg fp ON fp.anonymous_id = sc.anonymous_id AND fp.week = bb.week_start
)
SELECT
  CAST(week_start AS STRING) AS week_start,
  stage,
  canal_plat,
  device,
  ciudad,
  COUNT(DISTINCT backbone_uuid) AS n
FROM (
  SELECT
    week_start,
    'form_start' AS stage,
    CASE
      WHEN utm_source LIKE '%google%' AND utm_medium IN ('cpc','paid','ppc','paidsearch') THEN 'Google/Paid'
      WHEN utm_source LIKE '%google%' THEN 'Google/Organic'
      WHEN utm_source IN ('facebook','instagram','meta','fb','ig') AND utm_medium IN ('cpc','paid','ppc','paid_social','paidsocial') THEN 'Meta/Paid'
      WHEN utm_source IN ('facebook','instagram','meta','fb','ig') THEN 'Meta/Organic'
      WHEN utm_source LIKE '%bing%' THEN 'Bing/Paid'
      WHEN utm_source LIKE '%tiktok%' THEN 'TikTok/Paid'
      WHEN utm_source IS NULL OR utm_source = '' THEN 'Direct/Direct'
      ELSE 'Otro/Otro'
    END AS canal_plat,
    CASE
      WHEN is_mobile = TRUE AND ua_platform LIKE '%ipad%' THEN 'tablet'
      WHEN is_mobile = TRUE THEN 'mobile'
      WHEN is_mobile = FALSE THEN 'desktop'
      ELSE 'unknown'
    END AS device,
    IFNULL(ciudad_raw, 'Sin ciudad') AS ciudad,
    backbone_uuid
  FROM enriched
  UNION ALL
  SELECT
    week_start,
    'submit' AS stage,
    CASE
      WHEN utm_source LIKE '%google%' AND utm_medium IN ('cpc','paid','ppc','paidsearch') THEN 'Google/Paid'
      WHEN utm_source LIKE '%google%' THEN 'Google/Organic'
      WHEN utm_source IN ('facebook','instagram','meta','fb','ig') AND utm_medium IN ('cpc','paid','ppc','paid_social','paidsocial') THEN 'Meta/Paid'
      WHEN utm_source IN ('facebook','instagram','meta','fb','ig') THEN 'Meta/Organic'
      WHEN utm_source LIKE '%bing%' THEN 'Bing/Paid'
      WHEN utm_source LIKE '%tiktok%' THEN 'TikTok/Paid'
      WHEN utm_source IS NULL OR utm_source = '' THEN 'Direct/Direct'
      ELSE 'Otro/Otro'
    END AS canal_plat,
    CASE
      WHEN is_mobile = TRUE AND ua_platform LIKE '%ipad%' THEN 'tablet'
      WHEN is_mobile = TRUE THEN 'mobile'
      WHEN is_mobile = FALSE THEN 'desktop'
      ELSE 'unknown'
    END AS device,
    IFNULL(ciudad_raw, 'Sin ciudad') AS ciudad,
    backbone_uuid
  FROM enriched
  WHERE deal_uuid != '0' AND deal_uuid IS NOT NULL
) f
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 2, 3, 4
```

- [ ] **Step 2: Dry-run estimate**

```bash
bq query --use_legacy_sql=false --dry_run --format=prettyjson < funnel-web-mx/query_backbone.sql | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'GB scanned: {int(d[\"statistics\"][\"totalBytesProcessed\"])/1e9:.2f}')"
```

Expected: < 15 GB.

- [ ] **Step 3: Execute on a 14-day window**

```bash
bq query --use_legacy_sql=false --format=prettyjson --max_rows=20 "$(sed 's/INTERVAL 140 DAY/INTERVAL 14 DAY/g; s/INTERVAL 150 DAY/INTERVAL 20 DAY/g' funnel-web-mx/query_backbone.sql)"
```

Expected: rows with `stage` in {form_start, submit}, `canal_plat`/`device` populated, `n` decreasing from form_start to submit.

- [ ] **Step 4: Run full window**

```bash
bq query --use_legacy_sql=false --format=prettyjson --max_rows=20000 < funnel-web-mx/query_backbone.sql > /tmp/backbone_sample.json
python3 -c "import json; d=json.load(open('/tmp/backbone_sample.json')); print(f'rows: {len(d)}'); stages=set(r['stage'] for r in d); print('stages:', stages); ciudades=sorted({r['ciudad'] for r in d}); print(f'ciudades distintas: {len(ciudades)}, samples: {ciudades[:5]}')"
```

Expected: stages = {form_start, submit}, multiple ciudades distinct. If only "Sin ciudad" appears, zone extraction is broken — check JSON path in `bb` CTE.

- [ ] **Step 5: Commit**

```bash
git add funnel-web-mx/query_backbone.sql
git commit -m "query: funnel-web-mx form_start + submit (etapa 11)"
```

### Task 2.4: Write `query_leads.sql`

**Files:**
- Create: `funnel-web-mx/query_leads.sql`

- [ ] **Step 1: Write the SQL**

Write to `funnel-web-mx/query_leads.sql`:

```sql
-- Funnel Web MX — Lead registrado (etapa 13)
-- Source: papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general (fuente_id=3)
-- Joins with backbone + segment for UTM/device first-touch attribution
-- Output: one row per (week_start, canal_plat, device, ciudad, zona_grande, zona_mediana) with n_leads/cal/asg

WITH leads AS (
  SELECT
    g.nid,
    g.id_negocio AS deal_id_local,
    DATE_TRUNC(DATE(g.fecha_creacion, 'America/Mexico_City'), ISOWEEK) AS week_start,
    g.fecha_creacion,
    g.ciudad,
    g.zona_grande_label,
    g.zona_mediana_label,
    g.campana_mercadeo_original
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
  WHERE g.fuente_id = 3
    AND g.fecha_creacion >= TIMESTAMP(DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK))
    AND g.fecha_creacion < TIMESTAMP(DATE_TRUNC(CURRENT_DATE(), ISOWEEK))
),
deals_oltp AS (
  SELECT pd.nid, pd.uuid AS deal_uuid
  FROM `sellers-main-prod.mx_rds_staging.habi_db_property_deal` pd
  WHERE pd.nid IS NOT NULL
),
bb AS (
  SELECT uuid AS backbone_uuid, deal_uuid
  FROM `sellers-main-prod.top_funnel.web_global_api_business`
  WHERE country = 'MX' AND deal_uuid IS NOT NULL AND deal_uuid != '0'
),
sc AS (
  SELECT backbone_uuid,
    ARRAY_AGG(STRUCT(anonymous_id, timestamp) ORDER BY timestamp LIMIT 1)[OFFSET(0)].anonymous_id AS anonymous_id
  FROM `sellers-main-prod.mx_segment_profiles.select_content`
  WHERE backbone_uuid IS NOT NULL
    AND DATE(timestamp, 'America/Mexico_City') >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 150 DAY), ISOWEEK)
  GROUP BY 1
),
first_pg AS (
  SELECT
    anonymous_id,
    DATE_TRUNC(DATE(timestamp, 'America/Mexico_City'), ISOWEEK) AS week,
    ARRAY_AGG(STRUCT(
      LOWER(IFNULL(context_campaign_utm_source, '')) AS utm_source,
      LOWER(IFNULL(context_campaign_utm_medium, '')) AS utm_medium,
      context_user_agent_data_mobile AS is_mobile,
      LOWER(IFNULL(context_user_agent_data_platform, '')) AS ua_platform
    ) ORDER BY timestamp LIMIT 1)[OFFSET(0)] AS fe
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Mexico_City') >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK)
    AND DATE(timestamp, 'America/Mexico_City') < DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
    AND context_page_url LIKE '%habi.mx%'
    AND anonymous_id IS NOT NULL
  GROUP BY 1, 2
),
utm_dict AS (
  -- Fallback attribution by campana_mercadeo_original → UTM dict
  SELECT DISTINCT
    campana_mercadeo_original,
    mkt_channel_medium,
    mkt_platform
  FROM `sellers-main-prod.bi_mx.registro_unico_utm_mkt_mexico`
),
cal_dates AS (
  SELECT deal_id, MIN(date_create) AS cal_ts
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
  WHERE state_id IN (20, 63)
  GROUP BY 1
),
asg AS (
  SELECT DISTINCT a.nid
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` a
  WHERE a.pais = 'mexico'
    AND a.fuente_id_tig = 3
    AND a.dia >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK)
    AND a.dia < DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
),
enriched AS (
  SELECT
    l.nid,
    l.week_start,
    l.ciudad,
    l.zona_grande_label,
    l.zona_mediana_label,
    -- Primary attribution: segment chain
    fp.fe.utm_source,
    fp.fe.utm_medium,
    fp.fe.is_mobile,
    fp.fe.ua_platform,
    -- Fallback attribution: UTM dict via campana_mercadeo_original
    ud.mkt_platform AS fallback_platform,
    ud.mkt_channel_medium AS fallback_medium,
    -- Cal flag
    IF(cd.deal_id IS NOT NULL, 1, 0) AS is_cal,
    IF(asg.nid IS NOT NULL, 1, 0) AS is_asg
  FROM leads l
  LEFT JOIN deals_oltp d ON d.nid = l.nid
  LEFT JOIN bb ON bb.deal_uuid = d.deal_uuid
  LEFT JOIN sc ON sc.backbone_uuid = bb.backbone_uuid
  LEFT JOIN first_pg fp ON fp.anonymous_id = sc.anonymous_id AND fp.week = l.week_start
  LEFT JOIN utm_dict ud ON ud.campana_mercadeo_original = l.campana_mercadeo_original
  LEFT JOIN cal_dates cd ON cd.deal_id = l.deal_id_local
  LEFT JOIN asg ON asg.nid = l.nid
)
SELECT
  CAST(week_start AS STRING) AS week_start,
  CASE
    WHEN utm_source LIKE '%google%' AND utm_medium IN ('cpc','paid','ppc','paidsearch') THEN 'Google/Paid'
    WHEN utm_source LIKE '%google%' THEN 'Google/Organic'
    WHEN utm_source IN ('facebook','instagram','meta','fb','ig') AND utm_medium IN ('cpc','paid','ppc','paid_social','paidsocial') THEN 'Meta/Paid'
    WHEN utm_source IN ('facebook','instagram','meta','fb','ig') THEN 'Meta/Organic'
    WHEN utm_source LIKE '%bing%' THEN 'Bing/Paid'
    WHEN utm_source LIKE '%tiktok%' THEN 'TikTok/Paid'
    WHEN utm_source IS NOT NULL AND utm_source != '' THEN 'Otro/Otro'
    -- Fallback when segment chain missing
    WHEN LOWER(IFNULL(fallback_platform, '')) LIKE '%google%' AND LOWER(IFNULL(fallback_medium, '')) IN ('cpc','paid') THEN 'Google/Paid'
    WHEN LOWER(IFNULL(fallback_platform, '')) LIKE '%meta%' OR LOWER(IFNULL(fallback_platform, '')) LIKE '%facebook%' THEN 'Meta/Paid'
    WHEN LOWER(IFNULL(fallback_platform, '')) LIKE '%bing%' THEN 'Bing/Paid'
    WHEN LOWER(IFNULL(fallback_platform, '')) LIKE '%tiktok%' THEN 'TikTok/Paid'
    WHEN fallback_platform IS NOT NULL THEN 'Otro/Otro'
    ELSE 'Direct/Direct'
  END AS canal_plat,
  CASE
    WHEN is_mobile = TRUE AND ua_platform LIKE '%ipad%' THEN 'tablet'
    WHEN is_mobile = TRUE THEN 'mobile'
    WHEN is_mobile = FALSE THEN 'desktop'
    ELSE 'unknown'
  END AS device,
  IFNULL(ciudad, 'Sin ciudad') AS ciudad,
  IFNULL(zona_grande_label, 'Sin zona grande') AS zona_grande,
  IFNULL(zona_mediana_label, 'Sin zona mediana') AS zona_mediana,
  COUNT(DISTINCT nid) AS n_leads,
  SUM(is_cal) AS n_calificados,
  SUM(is_asg) AS n_asignados
FROM enriched
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY 1, 2, 3, 4
```

- [ ] **Step 2: Dry-run estimate**

```bash
bq query --use_legacy_sql=false --dry_run --format=prettyjson < funnel-web-mx/query_leads.sql | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'GB scanned: {int(d[\"statistics\"][\"totalBytesProcessed\"])/1e9:.2f}')"
```

Expected: < 20 GB.

- [ ] **Step 3: Execute on a 14-day window**

```bash
bq query --use_legacy_sql=false --format=prettyjson --max_rows=20 "$(sed 's/INTERVAL 140 DAY/INTERVAL 14 DAY/g; s/INTERVAL 150 DAY/INTERVAL 20 DAY/g' funnel-web-mx/query_leads.sql)"
```

Expected: rows with `canal_plat`/`device`/`ciudad`/`zona_grande`/`zona_mediana` populated, `n_leads` >= `n_calificados` >= `n_asignados` typically.

- [ ] **Step 4: Run full window and inspect**

```bash
bq query --use_legacy_sql=false --format=prettyjson --max_rows=50000 < funnel-web-mx/query_leads.sql > /tmp/leads_sample.json
python3 -c "
import json
d = json.load(open('/tmp/leads_sample.json'))
print(f'rows: {len(d)}')
print(f'total leads: {sum(int(r[\"n_leads\"]) for r in d)}')
print(f'ciudades distintas: {len({r[\"ciudad\"] for r in d})}')
print(f'canal_plat distintos: {sorted({r[\"canal_plat\"] for r in d})}')"
```

Expected: ~1000+ rows, total leads in the thousands per 140d, multiple ciudades.

- [ ] **Step 5: Commit**

```bash
git add funnel-web-mx/query_leads.sql
git commit -m "query: funnel-web-mx leads (etapa 13)"
```

---

## Phase 3 — Build script

### Task 3.1: Write `build_data.py`

**Files:**
- Create: `funnel-web-mx/build_data.py`

- [ ] **Step 1: Write the script**

Write to `funnel-web-mx/build_data.py`:

```python
#!/usr/bin/env python3
"""Merge 4 BQ query outputs into one data.json for the funnel-web-mx dashboard.

Usage:
  python3 build_data.py clicks.json sessions.json backbone.json leads.json out.json
"""
import json
import sys
from datetime import datetime, timezone
from collections import defaultdict

STAGES = [
    {"id": "click", "label": "Click reportado", "supports": ["canal_plat"]},
    {"id": "session", "label": "Sesion Segment", "supports": ["canal_plat", "device"]},
    {"id": "inicio", "label": "/inicio", "supports": ["canal_plat", "device"]},
    {"id": "zona", "label": "/inmuebles-zona", "supports": ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "confirmar_ubicacion", "label": "/confirmar-ubicacion-mx", "supports": ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "datos_inmueble", "label": "/datos-inmueble", "supports": ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "caracteristicas", "label": "/caracteristicas", "supports": ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "ultimos_detalles", "label": "/ultimos-detalles", "supports": ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "sugerencias", "label": "/sugerencias-de-propiedades", "supports": ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "contacto", "label": "/contacto", "supports": ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "submit", "label": "Form submit", "supports": ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "felicitaciones", "label": "/felicitaciones", "supports": ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]},
    {"id": "lead", "label": "Lead registrado", "supports": ["canal_plat", "device", "ciudad", "zona_grande", "zona_mediana"]},
]
STAGE_IDS = [s["id"] for s in STAGES]


def empty_week():
    return {
        "totals": {sid: 0 for sid in STAGE_IDS},
        "by_canal_plat": defaultdict(lambda: {sid: 0 for sid in STAGE_IDS}),
        "by_device": defaultdict(lambda: {sid: 0 for sid in STAGE_IDS}),
        "by_ciudad": defaultdict(lambda: {sid: 0 for sid in STAGE_IDS}),
        "by_zona_grande": defaultdict(lambda: {sid: 0 for sid in STAGE_IDS}),
        "by_zona_mediana": defaultdict(lambda: {sid: 0 for sid in STAGE_IDS}),
    }


def main(clicks_path, sessions_path, backbone_path, leads_path, out_path):
    clicks = json.load(open(clicks_path))
    sessions = json.load(open(sessions_path))
    backbone = json.load(open(backbone_path))
    leads = json.load(open(leads_path))

    by_week = defaultdict(empty_week)

    # 1) Clicks → stage 'click', cluster only by canal_plat (build plat label like "Google/Paid")
    for r in clicks:
        week = r["week_start"]
        plat = r["plataforma"]
        canal_plat = f"{plat}/Paid" if plat != "Otro" else "Otro/Otro"
        n = int(r["clicks"])
        by_week[week]["totals"]["click"] += n
        by_week[week]["by_canal_plat"][canal_plat]["click"] += n
        # No device or ciudad for click stage

    # 2) Sessions → stages session, inicio, zona, ..., felicitaciones (per query_sessions.sql)
    for r in sessions:
        week = r["week_start"]
        stage = r["stage"]
        canal_plat = r["canal_plat"]
        device = r["device"]
        n = int(r["n_visitors"])
        by_week[week]["totals"][stage] += n
        by_week[week]["by_canal_plat"][canal_plat][stage] += n
        by_week[week]["by_device"][device][stage] += n

    # 3) Backbone → stages form_start (not in spec funnel — skip) + submit
    # The spec funnel uses 'submit' from this query. form_start is not a spec etapa.
    for r in backbone:
        if r["stage"] != "submit":
            continue
        week = r["week_start"]
        canal_plat = r["canal_plat"]
        device = r["device"]
        ciudad = r["ciudad"]
        n = int(r["n"])
        by_week[week]["totals"]["submit"] += n
        by_week[week]["by_canal_plat"][canal_plat]["submit"] += n
        by_week[week]["by_device"][device]["submit"] += n
        if ciudad and ciudad != "Sin ciudad":
            by_week[week]["by_ciudad"][ciudad]["submit"] += n

    # 4) Leads → stage 'lead' (full cluster support including zona)
    for r in leads:
        week = r["week_start"]
        canal_plat = r["canal_plat"]
        device = r["device"]
        ciudad = r["ciudad"]
        zona_grande = r["zona_grande"]
        zona_mediana = r["zona_mediana"]
        n = int(r["n_leads"])
        by_week[week]["totals"]["lead"] += n
        by_week[week]["by_canal_plat"][canal_plat]["lead"] += n
        by_week[week]["by_device"][device]["lead"] += n
        by_week[week]["by_ciudad"][ciudad]["lead"] += n
        by_week[week]["by_zona_grande"][zona_grande]["lead"] += n
        by_week[week]["by_zona_mediana"][zona_mediana]["lead"] += n

    # Flatten defaultdicts to plain dicts for JSON serialization
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "weeks": sorted(by_week.keys()),
        "stages": STAGES,
        "by_week": {
            week: {
                "totals": w["totals"],
                "by_canal_plat": dict(w["by_canal_plat"]),
                "by_device": dict(w["by_device"]),
                "by_ciudad": dict(w["by_ciudad"]),
                "by_zona_grande": dict(w["by_zona_grande"]),
                "by_zona_mediana": dict(w["by_zona_mediana"]),
            }
            for week, w in by_week.items()
        },
    }

    with open(out_path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"weeks: {len(out['weeks'])}  range: {out['weeks'][0]} .. {out['weeks'][-1]}")
    print(f"latest totals: {out['by_week'][out['weeks'][-1]]['totals']}")


if __name__ == "__main__":
    if len(sys.argv) != 6:
        print(__doc__)
        sys.exit(1)
    main(*sys.argv[1:])
```

- [ ] **Step 2: Run against the samples from Phase 2**

Run:
```bash
# Re-fetch fresh full-window outputs (or reuse /tmp/*.json from Phase 2 if available)
bq query --use_legacy_sql=false --format=json --max_rows=200000 < funnel-web-mx/query_clicks.sql > /tmp/wfmx_clicks.json
bq query --use_legacy_sql=false --format=json --max_rows=200000 < funnel-web-mx/query_sessions.sql > /tmp/wfmx_sessions.json
bq query --use_legacy_sql=false --format=json --max_rows=200000 < funnel-web-mx/query_backbone.sql > /tmp/wfmx_backbone.json
bq query --use_legacy_sql=false --format=json --max_rows=200000 < funnel-web-mx/query_leads.sql > /tmp/wfmx_leads.json

python3 funnel-web-mx/build_data.py /tmp/wfmx_clicks.json /tmp/wfmx_sessions.json /tmp/wfmx_backbone.json /tmp/wfmx_leads.json funnel-web-mx/data.json
```

Expected stdout:
```
weeks: ~20  range: 2026-01-05 .. 2026-05-18
latest totals: {'click': 6digit, 'session': 5-6digit, 'inicio': 5-6digit, ..., 'lead': 4digit}
```

- [ ] **Step 3: Sanity-check data.json shape**

```bash
python3 -c "
import json
d = json.load(open('funnel-web-mx/data.json'))
assert 'updated' in d and 'weeks' in d and 'stages' in d and 'by_week' in d
assert len(d['stages']) == 13
latest = d['weeks'][-1]
w = d['by_week'][latest]
assert set(w.keys()) == {'totals','by_canal_plat','by_device','by_ciudad','by_zona_grande','by_zona_mediana'}
print('shape ok')
print('latest week:', latest)
print('totals:', w['totals'])
print('clusters in by_canal_plat:', sorted(w['by_canal_plat'].keys()))
print('clusters in by_device:', sorted(w['by_device'].keys()))
print('top 5 ciudades by lead:', sorted(w['by_ciudad'].items(), key=lambda kv: -kv[1].get('lead',0))[:5])
"
```

Expected: shape ok, sensible totals, canal_plat has multiple keys, device has at least mobile + desktop, ciudades has CDMX/Monterrey/etc.

- [ ] **Step 4: Commit**

```bash
git add funnel-web-mx/build_data.py funnel-web-mx/data.json
git commit -m "build: funnel-web-mx data builder + first data.json"
```

---

## Phase 4 — Frontend

The frontend is one file: `funnel-web-mx/index.html`. We'll build it incrementally with a working browser preview after each block.

### Task 4.1: Header scaffolding

**Files:**
- Modify: `funnel-web-mx/index.html`

- [ ] **Step 1: Write the initial scaffold**

Replace `funnel-web-mx/index.html` contents with:

```html
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📢</text></svg>">
<title>Funnel Web MX — Tableros Marketing</title>
<style>
  :root {
    --bg: #0f172a; --card: #1e293b; --border: #334155;
    --indigo: #818cf8; --amber: #f59e0b; --red: #ef4444;
    --text: #f8fafc; --text2: #e2e8f0; --muted: #94a3b8;
  }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }
  .back-link { display: inline-block; color: var(--indigo); text-decoration: none; margin-bottom: 16px; }
  .back-link:hover { text-decoration: underline; }
  h1 { margin: 0 0 4px; font-size: 24px; }
  .subtitle { color: var(--muted); margin: 0 0 24px; font-size: 14px; }
  .header-row { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
  .chip { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 6px 12px; font-size: 12px; color: var(--text2); }
  .chip.country { background: #1e3a8a; border-color: #3b82f6; }
  .chip.fresh { font-family: ui-monospace, monospace; }
  .week-pill { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; cursor: pointer; font-size: 13px; color: var(--text2); }
  .week-pill.active { background: var(--indigo); color: #0f172a; border-color: var(--indigo); font-weight: 600; }
  .week-pill:hover:not(.active) { border-color: var(--indigo); }
  .week-row { display: flex; gap: 6px; margin-bottom: 24px; flex-wrap: wrap; }
</style>
</head>
<body>
<a href="../" class="back-link">← Volver (Tableros Marketing Sellers)</a>
<h1>Funnel Web MX</h1>
<p class="subtitle">Diagnóstico de la caída click→registro en MX, fuente WEB, integrando tráfico real desde Segment.</p>

<div class="header-row">
  <span class="chip country">MX</span>
  <span class="chip fresh" id="freshness">Cargando…</span>
</div>

<div class="week-row" id="week-row"></div>

<div id="blocks">
  <!-- Bloques A, B, C aquí -->
</div>

<script>
let DATA = null;
let STATE = { weekStart: null, stageId: null, clusterDim: null, clusterValue: null };

function fmtAgo(iso) {
  const t = new Date(iso).getTime();
  const diffMin = Math.round((Date.now() - t) / 60000);
  if (diffMin < 60) return `hace ${diffMin}m`;
  const h = Math.round(diffMin / 60);
  if (h < 48) return `hace ${h}h`;
  const d = Math.round(h / 24);
  return `hace ${d}d`;
}

function fmtRange(weekStart) {
  const d = new Date(weekStart + 'T00:00:00Z');
  const end = new Date(d.getTime() + 6 * 86400000);
  const fmt = dt => dt.toISOString().slice(5, 10).replace('-', '/');
  return `${fmt(d)} – ${fmt(end)}`;
}

function renderHeader() {
  document.getElementById('freshness').textContent = `Actualizado ${fmtAgo(DATA.updated)} · ${DATA.updated}`;
  const row = document.getElementById('week-row');
  row.innerHTML = '';
  // Show last 6 weeks as pills
  const weeks = DATA.weeks.slice(-6);
  for (const w of weeks) {
    const p = document.createElement('div');
    p.className = 'week-pill' + (w === STATE.weekStart ? ' active' : '');
    p.textContent = fmtRange(w);
    p.onclick = () => { STATE.weekStart = w; render(); };
    row.appendChild(p);
  }
}

function render() {
  if (!DATA) return;
  if (!STATE.weekStart) STATE.weekStart = DATA.weeks[DATA.weeks.length - 1];
  renderHeader();
  // Blocks A, B, C rendered in later tasks
}

fetch('data.json?v=' + Date.now())
  .then(r => r.json())
  .then(d => { DATA = d; render(); })
  .catch(err => { document.getElementById('freshness').textContent = 'Error cargando data: ' + err; });
</script>
</body>
</html>
```

- [ ] **Step 2: Open in browser to verify**

Run:
```bash
cd funnel-web-mx
python3 -m http.server 8765 &
sleep 1
xdg-open http://localhost:8765/ 2>/dev/null || echo "Open http://localhost:8765/ manually"
```

Expected: page shows title, MX chip, "Actualizado hace Xm" chip with timestamp, 6 week pills, latest one active. Click each pill changes the active state.

- [ ] **Step 3: Stop server**

Run:
```bash
pkill -f "http.server 8765" 2>/dev/null
```

- [ ] **Step 4: Commit**

```bash
git add funnel-web-mx/index.html
git commit -m "ui: funnel-web-mx header + week selector"
```

### Task 4.2: Bloque A — Funnel principal

**Files:**
- Modify: `funnel-web-mx/index.html`

- [ ] **Step 1: Add CSS for Bloque A**

Insert these rules INSIDE the existing `<style>` block, just before `</style>`:

```css
  .block { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 24px; }
  .block-title { margin: 0 0 16px; font-size: 16px; font-weight: 600; }
  .stage-row { display: grid; grid-template-columns: 200px 1fr 100px 90px; gap: 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); cursor: pointer; }
  .stage-row:last-child { border-bottom: none; }
  .stage-row:hover { background: rgba(129, 140, 248, 0.05); }
  .stage-row.active { background: rgba(129, 140, 248, 0.15); }
  .stage-label { font-size: 13px; color: var(--text2); }
  .stage-bar-wrap { background: #0b1220; border-radius: 4px; height: 18px; overflow: hidden; }
  .stage-bar { background: var(--indigo); height: 100%; transition: width 0.3s; }
  .stage-value { font-family: ui-monospace, monospace; font-size: 13px; text-align: right; }
  .stage-drop { font-size: 11px; padding: 2px 8px; border-radius: 4px; text-align: center; font-family: ui-monospace, monospace; }
  .drop-low { background: #1e293b; color: var(--muted); }
  .drop-mid { background: #78350f; color: var(--amber); }
  .drop-high { background: #7f1d1d; color: var(--red); }
```

- [ ] **Step 2: Add HTML container for Bloque A**

Replace the `<div id="blocks">` line with:

```html
<div id="blocks">
  <div class="block">
    <h2 class="block-title">Funnel — semana seleccionada</h2>
    <div id="funnel-rows"></div>
  </div>
</div>
```

- [ ] **Step 3: Add the render function for Bloque A**

Inside the `<script>` block, before the line `function render() {`, add:

```javascript
function fmtN(n) {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
  return String(n);
}

function dropClass(pct) {
  if (pct < 30) return 'drop-low';
  if (pct < 70) return 'drop-mid';
  return 'drop-high';
}

function getStageValue(weekData, stageId) {
  if (STATE.clusterDim && STATE.clusterValue) {
    const cluster = weekData['by_' + STATE.clusterDim] || {};
    return (cluster[STATE.clusterValue] || {})[stageId] || 0;
  }
  return weekData.totals[stageId] || 0;
}

function renderBlockA() {
  const container = document.getElementById('funnel-rows');
  container.innerHTML = '';
  const week = DATA.by_week[STATE.weekStart];
  if (!week) return;
  const values = DATA.stages.map(s => ({ id: s.id, label: s.label, n: getStageValue(week, s.id) }));
  const maxN = Math.max(...values.map(v => v.n), 1);
  const maxLog = Math.log10(maxN + 1);
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    const prev = i > 0 ? values[i - 1].n : null;
    const dropPct = (prev && prev > 0) ? Math.round((1 - v.n / prev) * 100) : null;
    const barWidth = v.n > 0 ? (Math.log10(v.n + 1) / maxLog * 100) : 0;
    const row = document.createElement('div');
    row.className = 'stage-row' + (STATE.stageId === v.id ? ' active' : '');
    row.onclick = () => { STATE.stageId = STATE.stageId === v.id ? null : v.id; render(); };
    row.innerHTML = `
      <div class="stage-label">${v.label}</div>
      <div class="stage-bar-wrap"><div class="stage-bar" style="width: ${barWidth}%"></div></div>
      <div class="stage-value">${fmtN(v.n)}</div>
      <div class="stage-drop ${dropPct !== null ? dropClass(dropPct) : 'drop-low'}">${dropPct !== null ? '↓' + dropPct + '%' : '—'}</div>
    `;
    container.appendChild(row);
  }
}
```

- [ ] **Step 4: Hook renderBlockA into render()**

Replace the current `function render()` body with:

```javascript
function render() {
  if (!DATA) return;
  if (!STATE.weekStart) STATE.weekStart = DATA.weeks[DATA.weeks.length - 1];
  renderHeader();
  renderBlockA();
}
```

- [ ] **Step 5: Open browser, verify**

```bash
cd funnel-web-mx && python3 -m http.server 8765 &
sleep 1 && xdg-open http://localhost:8765/ 2>/dev/null || echo "Open manually"
```

Expected: 13 stage rows visible, each with name, bar, value, drop% badge. Click a pill → numbers update. Click a stage row → it highlights.

- [ ] **Step 6: Stop server, commit**

```bash
pkill -f "http.server 8765" 2>/dev/null
git add funnel-web-mx/index.html
git commit -m "ui: funnel-web-mx bloque A (funnel principal)"
```

### Task 4.3: Bloque B — Sparklines 20 semanas

**Files:**
- Modify: `funnel-web-mx/index.html`

- [ ] **Step 1: Add CSS for sparklines**

Insert in `<style>` before `</style>`:

```css
  .sparks-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
  .spark-card { background: #0b1220; border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
  .spark-card .spark-label { font-size: 11px; color: var(--muted); margin-bottom: 4px; }
  .spark-card .spark-value { font-family: ui-monospace, monospace; font-size: 18px; margin-bottom: 8px; }
  .spark-card svg { width: 100%; height: 40px; }
  .spark-line { stroke: var(--indigo); stroke-width: 1.5; fill: none; }
  .spark-dot-last { fill: var(--amber); }
```

- [ ] **Step 2: Add Bloque B container**

Inside `<div id="blocks">`, after the Bloque A `<div class="block">...</div>`, add:

```html
  <div class="block">
    <h2 class="block-title">Tendencia 20 semanas — hitos clave</h2>
    <div class="sparks-row" id="sparks-row"></div>
  </div>
```

- [ ] **Step 3: Add renderBlockB**

In `<script>`, before `function render()`, add:

```javascript
const SPARK_STAGES = ['click', 'session', 'inicio', 'contacto', 'lead'];

function sparkPath(values) {
  if (!values.length) return '';
  const max = Math.max(...values, 1);
  const W = 100, H = 40;
  const step = W / (values.length - 1 || 1);
  return values.map((v, i) => `${i === 0 ? 'M' : 'L'} ${(i * step).toFixed(1)} ${(H - (v / max) * H).toFixed(1)}`).join(' ');
}

function renderBlockB() {
  const row = document.getElementById('sparks-row');
  row.innerHTML = '';
  const weeks = DATA.weeks;
  for (const stageId of SPARK_STAGES) {
    const stage = DATA.stages.find(s => s.id === stageId);
    const values = weeks.map(w => getStageValue(DATA.by_week[w] || {}, stageId));
    const last = values[values.length - 1] || 0;
    const card = document.createElement('div');
    card.className = 'spark-card';
    const W = 100, H = 40;
    const max = Math.max(...values, 1);
    const lastX = ((values.length - 1) / (values.length - 1 || 1)) * W;
    const lastY = H - (last / max) * H;
    card.innerHTML = `
      <div class="spark-label">${stage.label}</div>
      <div class="spark-value">${fmtN(last)}</div>
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><path class="spark-line" d="${sparkPath(values)}" /><circle class="spark-dot-last" cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="2" /></svg>
    `;
    row.appendChild(card);
  }
}
```

- [ ] **Step 4: Hook into render()**

Update `function render()`:

```javascript
function render() {
  if (!DATA) return;
  if (!STATE.weekStart) STATE.weekStart = DATA.weeks[DATA.weeks.length - 1];
  renderHeader();
  renderBlockA();
  renderBlockB();
}
```

- [ ] **Step 5: Verify in browser**

```bash
cd funnel-web-mx && python3 -m http.server 8765 &
sleep 1
```

Expected: 5 small sparkline cards in a row, each with label, value, and a tiny chart with an amber dot at the right end.

- [ ] **Step 6: Stop server, commit**

```bash
pkill -f "http.server 8765" 2>/dev/null
git add funnel-web-mx/index.html
git commit -m "ui: funnel-web-mx bloque B (sparklines)"
```

### Task 4.4: Bloque C — Tabla de clusters

**Files:**
- Modify: `funnel-web-mx/index.html`

- [ ] **Step 1: Add CSS**

Insert in `<style>`:

```css
  .tabs { display: flex; gap: 4px; margin-bottom: 12px; }
  .tab { background: transparent; border: 1px solid var(--border); border-radius: 6px; padding: 6px 14px; color: var(--text2); cursor: pointer; font-size: 13px; }
  .tab.active { background: var(--indigo); color: var(--bg); border-color: var(--indigo); font-weight: 600; }
  .cluster-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .cluster-table th, .cluster-table td { padding: 8px; text-align: right; border-bottom: 1px solid var(--border); }
  .cluster-table th:first-child, .cluster-table td:first-child { text-align: left; }
  .cluster-table th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
  .cluster-table tbody tr { cursor: pointer; }
  .cluster-table tbody tr:hover { background: rgba(129, 140, 248, 0.05); }
  .cluster-table tbody tr.active { background: rgba(129, 140, 248, 0.15); }
  .clear-filter-btn { background: transparent; border: 1px solid var(--border); border-radius: 6px; padding: 4px 10px; color: var(--muted); font-size: 11px; cursor: pointer; margin-left: 8px; }
  .clear-filter-btn:hover { color: var(--text); }
```

- [ ] **Step 2: Add Bloque C container**

In the HTML, after Bloque B, add:

```html
  <div class="block">
    <h2 class="block-title">Comparativa por cluster <button id="clear-filter" class="clear-filter-btn" style="display:none">Limpiar filtro</button></h2>
    <div class="tabs">
      <button class="tab active" data-dim="canal_plat">Canal / Plataforma</button>
      <button class="tab" data-dim="device">Device</button>
      <button class="tab" data-dim="ciudad">Zona — Ciudad</button>
      <button class="tab" data-dim="zona_grande">Zona — Grande</button>
      <button class="tab" data-dim="zona_mediana">Zona — Mediana</button>
    </div>
    <table class="cluster-table" id="cluster-table"></table>
  </div>
```

- [ ] **Step 3: Add renderBlockC**

In `<script>`:

```javascript
let CURRENT_DIM = 'canal_plat';
const CLUSTER_COLS = ['click', 'session', 'inicio', 'contacto', 'submit', 'lead'];

function renderBlockC() {
  const week = DATA.by_week[STATE.weekStart];
  if (!week) return;
  const dim = CURRENT_DIM;
  const clusterMap = week['by_' + dim] || {};
  const rows = Object.entries(clusterMap)
    .map(([k, stages]) => ({ key: k, ...stages }))
    .sort((a, b) => (b.lead || 0) - (a.lead || 0))
    .slice(0, 15);

  const colLabels = CLUSTER_COLS.map(id => DATA.stages.find(s => s.id === id).label);
  let html = '<thead><tr><th>' + dim.replace('_', ' ') + '</th>';
  for (const lbl of colLabels) html += `<th>${lbl}</th>`;
  html += '<th>Click→Lead</th></tr></thead><tbody>';
  for (const r of rows) {
    const isActive = STATE.clusterDim === dim && STATE.clusterValue === r.key;
    const cl_lead_pct = r.click > 0 ? ((r.lead || 0) / r.click * 100).toFixed(2) + '%' : '—';
    html += `<tr class="${isActive ? 'active' : ''}" data-key="${r.key.replace(/"/g, '&quot;')}">`;
    html += `<td>${r.key}</td>`;
    for (const c of CLUSTER_COLS) html += `<td>${fmtN(r[c] || 0)}</td>`;
    html += `<td>${cl_lead_pct}</td></tr>`;
  }
  html += '</tbody>';
  const table = document.getElementById('cluster-table');
  table.innerHTML = html;
  table.querySelectorAll('tbody tr').forEach(tr => {
    tr.onclick = () => {
      const key = tr.getAttribute('data-key');
      if (STATE.clusterDim === dim && STATE.clusterValue === key) {
        STATE.clusterDim = null;
        STATE.clusterValue = null;
      } else {
        STATE.clusterDim = dim;
        STATE.clusterValue = key;
      }
      render();
    };
  });
  document.getElementById('clear-filter').style.display = (STATE.clusterValue ? 'inline-block' : 'none');
}

document.addEventListener('click', (e) => {
  if (e.target.matches('.tab')) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    e.target.classList.add('active');
    CURRENT_DIM = e.target.getAttribute('data-dim');
    render();
  }
  if (e.target.id === 'clear-filter') {
    STATE.clusterDim = null;
    STATE.clusterValue = null;
    render();
  }
});
```

- [ ] **Step 4: Hook into render()**

Update:
```javascript
function render() {
  if (!DATA) return;
  if (!STATE.weekStart) STATE.weekStart = DATA.weeks[DATA.weeks.length - 1];
  renderHeader();
  renderBlockA();
  renderBlockB();
  renderBlockC();
}
```

- [ ] **Step 5: Verify in browser**

```bash
cd funnel-web-mx && python3 -m http.server 8765 &
sleep 1
```

Expected:
- Tabla con 5 pestañas; pestaña activa es Canal/Plataforma.
- Filas ordenadas por leads desc, máximo 15.
- Click en una fila filtra los bloques A y B (los números bajan).
- Aparece botón "Limpiar filtro".
- Cambiar pestaña a Device → muestra Mobile/Desktop/Tablet/unknown.
- Cambiar a Ciudad/Zona grande/Zona mediana → muestra zonas del inmueble.

- [ ] **Step 6: Stop server, commit**

```bash
pkill -f "http.server 8765" 2>/dev/null
git add funnel-web-mx/index.html
git commit -m "ui: funnel-web-mx bloque C (tabla de clusters)"
```

---

## Phase 5 — CI integration

### Task 5.1: Add steps to workflow

**Files:**
- Modify: `.github/workflows/update-data.yml`

- [ ] **Step 1: Add the 4 query steps + build step**

Insert into `.github/workflows/update-data.yml`, after the existing "Build calificados-mm-inmo/data.json" step but BEFORE the "Commit and push" step. Use exact YAML formatting matching surrounding context (2-space indent, `if: always()`).

The steps to add:

```yaml
      - name: Query funnel-web-mx — clicks (MX)
        if: always()
        run: |
          bq query --use_legacy_sql=false --format=json --max_rows=200000 < funnel-web-mx/query_clicks.sql > /tmp/wfmx_clicks.json

      - name: Query funnel-web-mx — sessions (MX)
        if: always()
        run: |
          bq query --use_legacy_sql=false --format=json --max_rows=500000 < funnel-web-mx/query_sessions.sql > /tmp/wfmx_sessions.json

      - name: Query funnel-web-mx — backbone (MX)
        if: always()
        run: |
          bq query --use_legacy_sql=false --format=json --max_rows=500000 < funnel-web-mx/query_backbone.sql > /tmp/wfmx_backbone.json

      - name: Query funnel-web-mx — leads (MX)
        if: always()
        run: |
          bq query --use_legacy_sql=false --format=json --max_rows=500000 < funnel-web-mx/query_leads.sql > /tmp/wfmx_leads.json

      - name: Build funnel-web-mx/data.json
        if: always()
        run: |
          python3 funnel-web-mx/build_data.py /tmp/wfmx_clicks.json /tmp/wfmx_sessions.json /tmp/wfmx_backbone.json /tmp/wfmx_leads.json funnel-web-mx/data.json
```

- [ ] **Step 2: Add the new data.json to the git add line**

In the "Commit and push" step, find this line:

```yaml
          git add incompletos-colombia/data.json tablero-marketing/data.json tablero-marketing/antifunnel.json tablero-marketing/mm_sin_inmo_states.json okr-marketing/data.json pmax-mexico-quality/data.json pmax-mexico-quality/states.json creativo-pamela/data.json incompletos-direccion/data.json marketing-wbr/data.json wbr-2-0/data.json asignados-creacion/data.json prioridad-mm/data.json funnel-fuentes/data.json calificados-mm-inmo/data.json
```

Append ` funnel-web-mx/data.json` to the end of the file list (one space before).

- [ ] **Step 3: Also bump cron to every 4h while editing the file**

Find:
```yaml
    - cron: '0 13 * * *'  # 7:00 AM México (UTC-6) / 8:00 AM Colombia (UTC-5)
```

Replace with:
```yaml
    - cron: '0 */4 * * *'  # Cada 4h UTC — cubre 06:00/10:00 CO el lunes para tablero semanal
```

- [ ] **Step 4: Commit and trigger workflow**

```bash
git add .github/workflows/update-data.yml
git commit -m "ci: agregar funnel-web-mx al workflow + cron cada 4h"
git push origin main
gh workflow run update-data.yml --ref main
sleep 5
gh run list --workflow=update-data.yml --limit 2
```

Expected: a new in_progress run appears.

- [ ] **Step 5: Wait for completion and verify**

```bash
# Wait for the in_progress run to finish (max ~5 min)
gh run watch $(gh run list --workflow=update-data.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

Expected: completes with success. After completion:

```bash
git pull --ff-only origin main
python3 -c "
import json
d = json.load(open('funnel-web-mx/data.json'))
print('updated:', d['updated'])
print('weeks:', len(d['weeks']), d['weeks'][0], '..', d['weeks'][-1])
print('latest totals:', d['by_week'][d['weeks'][-1]]['totals'])
"
```

Expected: updated timestamp is recent, weeks range includes 2026-05-18 (or whatever is the latest closed ISO week at the time).

### Task 5.2: Add card to landing index

**Files:**
- Modify: `index.html` (root)

- [ ] **Step 1: Find the right spot**

Per the user memory `feedback_hub_orden.md`: nuevos tableros van al **final** de la columna "Tableros" (orden cronológico ascendente).

Inspect the file:

```bash
grep -n "class=\"card\"" index.html | tail -10
```

Identify the last `<a class="card">` block in the "Tableros" column.

- [ ] **Step 2: Add a new card right after that last existing one**

Insert (matching the style of the other cards — use the same className/structure as `wbr-2-0/`):

```html
        <a class="card" href="funnel-web-mx/">
          <div class="card-title">🔬 Funnel Web MX</div>
          <div class="card-desc">Diagnóstico paso a paso de la caída click→registro en MX WEB, con tráfico real desde Segment.</div>
        </a>
```

(Adjust HTML structure if the existing cards use a different schema — examine the existing cards' markup and replicate exactly.)

- [ ] **Step 3: Verify in browser**

```bash
python3 -m http.server 8765 &
sleep 1
xdg-open http://localhost:8765/ 2>/dev/null || echo "Open manually"
```

Expected: new card appears as the last item in Tableros column. Click navigates to /funnel-web-mx/ correctly.

- [ ] **Step 4: Stop server, commit**

```bash
pkill -f "http.server 8765" 2>/dev/null
git add index.html
git commit -m "landing: agregar card Funnel Web MX"
git push origin main
```

---

## Phase 6 — Live verification

### Task 6.1: Verify on GitHub Pages

**Files:** none (live verification)

- [ ] **Step 1: Wait for GitHub Pages to rebuild**

GH Pages typically rebuilds within 1-2 minutes of a push to main.

```bash
sleep 90
```

- [ ] **Step 2: Open the live dashboard**

```bash
xdg-open https://camotoya.github.io/tableros-marketing-habi/funnel-web-mx/ 2>/dev/null || echo "Open the URL manually in browser"
```

Verify:
- Header chips render (MX + actualizado hace Xh).
- 6 week pills, latest active by default.
- Bloque A: 13 stage rows, declining values, drop% badges colored.
- Bloque B: 5 sparklines with last-point amber dots.
- Bloque C: tabla de clusters con 5 pestañas funcionando.
- Click en pestaña Device → switches table to Mobile/Desktop/Tablet.
- Click en fila de tabla → filtra bloques A y B (los números bajan al cluster).
- Botón "Limpiar filtro" aparece y funciona.
- Botón back link "← Volver" funciona.

- [ ] **Step 3: Validate the hypothesis from the original prompt**

Sanity check that the funnel reveals where the click→register drop is:

1. Filter cluster to **Canal/Plataforma = Google/Paid** (or whatever paid platform shows the drop in WBR 2.0).
2. Observe the funnel: where is the biggest drop% badge?
3. If the drop is in `Click → Sesión Segment`: platform-reported clicks are inflated (fraud, mis-attribution, or bot traffic). Conclusion = invertir en hablar con la plataforma o cambiar de campaign.
4. If the drop is in `Sesión → /inicio`: the landing page isn't routing traffic to the form. Conclusion = arreglar la landing.
5. If the drop is `/inicio → /inmuebles-zona`: form abandonment at step 0. Conclusion = product issue en la primera vista del form.

Document the finding in a short note (paste into chat or save).

- [ ] **Step 4: If issues found**

Document any rendering/data issues. Common gotchas:
- `data.json` cache: append `?v=` query string if browser shows stale data.
- Missing UTM in some platforms: shows up as `Direct/Direct` — flag if % is unexpectedly high (>50%).
- `Sin ciudad` row dominates zone tab: zone JSON extraction in `query_backbone.sql` might be using the wrong path; revisit Task 0.2 findings.

---

## Self-review

- ✅ All 13 etapas from the spec have a task implementing them (queries cover click/session/8 form steps/submit/lead).
- ✅ All 3 cluster dimensions (canal/plataforma, device, zona) are implemented in queries and frontend.
- ✅ JSON shape matches the spec exactly (`updated`, `weeks`, `stages`, `by_week`).
- ✅ Workflow integration uses the existing consolidated pattern.
- ✅ Cron change to every 4h is included (Task 5.1 Step 3).
- ✅ Landing card placement follows `feedback_hub_orden.md` (al final).
- ✅ No placeholders — every SQL, every line of Python and HTML is concrete.
- ✅ Verification steps included throughout, both query-level (dry-run scan + sample inspection) and UI-level (browser preview after each block).
- ✅ Risks from spec (partition, zone JSON, chain coverage, canal_adquisicion mapping) are addressed in Phase 0 validations.

The plan is ready for execution.
