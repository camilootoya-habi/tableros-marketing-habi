# Asignados — Explorador de Filtros · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `asignados-filtros` dashboard for CO that lets the user toggle each of the 16 filters defined by the WBR mart and see how the universe of "leads asignados" changes, with the official mart as a fixed reference line.

**Architecture:** Static dashboard following the same pattern as `wbr-2-0` and `marketing-wbr`: one BigQuery SQL → Python builder script → compact `data.json` with bitmask-encoded filter flags → vanilla HTML/CSS/JS that interprets toggles in the browser. Auto-updates daily via the consolidated GitHub Actions workflow.

**Tech Stack:** BigQuery (SQL), Python 3 (stdlib only), vanilla HTML/CSS/JS (no framework, no build step), GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-05-11-asignados-filtros-design.md`

**Repo conventions to follow:**
- Working directory: `~/habi/tableros-marketing/`
- Subfolder: `asignados-filtros/`
- Theme variables, favicon, back-link: copy pattern from `wbr-2-0/index.html`
- Workflow: `.github/workflows/update-data.yml` (consolidated, cron 13:00 UTC)
- Commits: imperative English, no `Auto-update` prefix (those are bot-only). Include `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer.

**Bitmask reminder (13 toggleable bits, F1/F2/F16 are structural and always on):**

| bit | filter | semantics |
|---|---|---|
| 0 | F3 (`@habi.`)         | AND |
| 1 | F4 (no agente/delta/call) | AND |
| 2 | F5 (no hardcoded emails)  | AND |
| 3 | F6 (special owners → contacto_digital) | AND |
| 4 | F7 estado=sin pricing incial | OR within state group |
| 5 | F8 estado=no gestionado      | OR within state group |
| 6 | F9 estado=cierre             | OR within state group |
| 7 | F10 estado=no hay suficientes datos | OR within state group |
| 8 | F11 (calificación ≠ N/NH) | AND |
| 9 | F12 (check_a_pricing=1)  | AND |
| 10 | F13 (fecha_creacion not null) | AND |
| 11 | F14 (nid not null)            | AND |
| 12 | F15 (asignacion_descartes_top null) | AND |

`STATE_MASK = 0b00011110000 = 240`. `OTHER_MASK = 0b1111100001111 = 7951`. `ALL_ON = 0b1111111111111 = 8191`.

---

## File Structure

```
asignados-filtros/
├── query.sql          ← BQ: pre-aggregated rows (d, bitmask, c, f, n)
├── build_data.py      ← BQ JSON → data.json with filters metadata
├── data.json          ← auto-generated, committed by workflow
└── index.html         ← UI (controls, panel, chart, table, calificación block)
```

Modified files outside `asignados-filtros/`:
- `index.html` (root): add card linking to the new dashboard
- `.github/workflows/update-data.yml`: add 2 new steps (query + build) + add `asignados-filtros/data.json` to commit step

---

## Task 1: Folder skeleton + SQL query

**Files:**
- Create: `asignados-filtros/query.sql`

- [ ] **Step 1: Create the folder**

```bash
cd ~/habi/tableros-marketing
mkdir -p asignados-filtros
```

- [ ] **Step 2: Write `asignados-filtros/query.sql`**

```sql
-- Asignados — Explorador de Filtros (CO)
-- Output: one row per (fecha_asignacion, bitmask, calificado, fuente_label) with COUNT.
-- Window: last 540 days (covers 18 months for monthly granularity).
-- F1+F2+F16 applied as structural filters (universe base).
-- 13 toggleable flags packed into a bitmask (bit 0 = F3, ..., bit 12 = F15).

DECLARE fecha_inicio DATE DEFAULT DATE_SUB(CURRENT_DATE(), INTERVAL 540 DAY);

WITH
-- F1 + F2: first hubspot_owner_id change per nid, F16 applied (UTC-5).
asignaciones_base AS (
  SELECT
    nid,
    DATETIME_SUB(fecha, INTERVAL 5 HOUR) AS fecha_asignacion_co,
    valor AS owner_id_raw
  FROM `papyrus-master.src_sellers_hubspot.history`
  WHERE propiedad = 'hubspot_owner_id'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY fecha ASC) = 1
),

asignaciones_ventana AS (
  SELECT *
  FROM asignaciones_base
  WHERE DATE(fecha_asignacion_co) >= fecha_inicio
),

asignaciones_con_email AS (
  SELECT
    a.nid,
    a.fecha_asignacion_co,
    LOWER(IFNULL(sc.email, a.owner_id_raw)) AS owner_email_lower
  FROM asignaciones_ventana a
  LEFT JOIN `papyrus-data.habi_wh_bi.sc_users_hubspot` sc
    ON a.owner_id_raw = CAST(sc.id_segundario AS STRING)
),

calificados AS (
  SELECT DISTINCT CAST(negocio_id AS STRING) AS nid
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
  WHERE estado_id IN (20, 63)
),

deal_info AS (
  SELECT
    CAST(nid AS STRING) AS nid,
    LOWER(TRIM(estado)) AS estado_lower,
    contacto_digital
  FROM `papyrus-staging.src_sellers_hubspot.deal`
),

inmueble_info AS (
  SELECT
    CAST(nid AS STRING) AS nid,
    fuente_id,
    LOWER(TRIM(calificacion_del_lead_v2)) AS calificacion_lower,
    check_a_pricing,
    fecha_creacion
    -- F15 (asignacion_descartes_top) intencionalmente omitido en v1
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general`
),

con_flags AS (
  SELECT
    DATE(a.fecha_asignacion_co) AS fecha_asignacion,
    IF(c.nid IS NOT NULL, 1, 0) AS calificado,
    CASE
      WHEN i.fuente_id = 7 THEN 'Habimetro'
      WHEN i.fuente_id = 20 THEN 'CRM'
      WHEN i.fuente_id = 39 THEN 'Broker'
      WHEN i.fuente_id = 3 THEN 'WEB'
      WHEN i.fuente_id = 1 THEN 'Ventanas'
      WHEN i.fuente_id IN (47, 37, 41, 42) THEN 'Leadform'
      ELSE 'Otro'
    END AS fuente_label,
    (
      -- bit 0: F3 correo contiene "habi."
      IF(a.owner_email_lower LIKE '%habi.%', 1, 0)
      -- bit 1: F4 no contiene agente/delta/call
      + IF(a.owner_email_lower NOT LIKE '%agente%'
           AND a.owner_email_lower NOT LIKE '%delta%'
           AND a.owner_email_lower NOT LIKE '%call%', 2, 0)
      -- bit 2: F5 no en hardcoded list
      + IF(a.owner_email_lower NOT IN (
             'alejandroaguirre@habi.co',
             'erickcastillo@tuhabi.mx',
             'victorialechtig@tuhabi.mx'), 4, 0)
      -- bit 3: F6 special owners require contacto_digital
      + IF(a.owner_email_lower NOT IN (
             'lauracruz@habi.co','alejandrobravo@habi.co',
             'juanquinones@habi.co','juanarcos@habi.co')
           OR d.contacto_digital IS NOT NULL, 8, 0)
      -- bit 4: F7 estado=sin pricing incial
      + IF(d.estado_lower = 'sin pricing incial', 16, 0)
      -- bit 5: F8 estado=no gestionado
      + IF(d.estado_lower = 'no gestionado', 32, 0)
      -- bit 6: F9 estado=cierre
      + IF(d.estado_lower = 'cierre', 64, 0)
      -- bit 7: F10 estado=no hay suficientes datos para comparar
      + IF(d.estado_lower = 'no hay suficientes datos para comparar', 128, 0)
      -- bit 8: F11 calificación NOT IN (n, nh)
      + IF(IFNULL(i.calificacion_lower, '') NOT IN ('n', 'nh'), 256, 0)
      -- bit 9: F12 check_a_pricing = 1
      + IF(i.check_a_pricing = 1, 512, 0)
      -- bit 10: F13 fecha_creacion no nula
      + IF(i.fecha_creacion IS NOT NULL, 1024, 0)
      -- bit 11: F14 nid no nulo
      + IF(i.nid IS NOT NULL, 2048, 0)
      -- bit 12: F15 (dummy en v1 — columna asignacion_descartes_top no accesible)
      + 4096
    ) AS bitmask
  FROM asignaciones_con_email a
  LEFT JOIN deal_info d ON a.nid = d.nid
  LEFT JOIN inmueble_info i ON a.nid = i.nid
  LEFT JOIN calificados c ON a.nid = c.nid
)

SELECT
  fecha_asignacion AS d,
  bitmask AS m,
  calificado AS c,
  fuente_label AS f,
  COUNT(*) AS n
FROM con_flags
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC, 2, 3, 4
```

- [ ] **Step 3: Smoke-test the query in BigQuery**

```bash
bq query --use_legacy_sql=false --max_rows=20 --format=pretty \
  < asignados-filtros/query.sql
```

Expected: 20 rows showing recent days, each with `d`, `m`, `c`, `f`, `n`. Sanity checks:
- Most recent `d` should be CURRENT_DATE - 1 (yesterday) or today's date if data is fresh
- `n` per row should be small (1–100); the table is highly granular
- `m` values should be diverse (not all 8191)

- [ ] **Step 4: Validate paridad with the official mart**

Run this counter-check to compare "all filters on" count vs the mart:

```bash
bq query --use_legacy_sql=false --format=pretty <<'SQL'
WITH explorer AS (
  -- paste the full query.sql here OR run it as subquery
  SELECT * FROM (
    -- inline: run the same query but only keep m=8191 rows for last 30 days
    SELECT d, SUM(n) AS n_explorer
    FROM (
      /* paste the whole query.sql output as a subquery */
    )
    WHERE (m & 7951) = 7951 AND (m & 240) > 0 AND d >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    GROUP BY d
  )
),
mart AS (
  SELECT DATE(fecha_dia) AS d, COUNT(*) AS n_mart
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE pais = 'colombia'
    AND DATE(fecha_dia) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  GROUP BY 1
)
SELECT
  COALESCE(e.d, m.d) AS d,
  e.n_explorer,
  m.n_mart,
  e.n_explorer - m.n_mart AS diff
FROM explorer e
FULL OUTER JOIN mart m ON e.d = m.d
ORDER BY d DESC
LIMIT 30
SQL
```

Expected: `diff` should be 0 (or within ±5) for most days. If diff is consistently large, there's a discrepancy in flag logic to investigate before continuing. Note the diff and proceed — small drift is acceptable for v1 if the cause is identifiable (e.g., the mart computes daily one cycle later).

If you don't want to paste the query inline, write the diff as a separate ad-hoc query — it's a one-shot validation, not committed.

- [ ] **Step 5: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignados-filtros/query.sql
git commit -m "$(cat <<'EOF'
Asignados filtros: SQL query with bitmask-encoded filter flags

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Build script (Python)

**Files:**
- Create: `asignados-filtros/build_data.py`

- [ ] **Step 1: Write `asignados-filtros/build_data.py`**

```python
#!/usr/bin/env python3
"""
Builds asignados-filtros/data.json from the BQ JSON output of query.sql.

Usage:
  build_data.py <bq_query_output.json> <output_data.json>

Input shape (BQ --format=json): list of objects with string fields:
  {"d": "2026-05-10", "m": "8191", "c": "1", "f": "Habimetro", "n": "42"}

Output shape: see asignados-filtros/data.json structure in the spec.
"""
import json
import sys
from datetime import datetime, timezone


FILTERS = [
    {"id": "F3",  "bit": 0,  "group": "Correo",   "label": "Correo @habi.",
     "tooltip": "El correo del owner debe contener \"habi.\" (cubre @habi.co y @tuhabi.mx)."},
    {"id": "F4",  "bit": 1,  "group": "Correo",   "label": "Excluye agente/delta/call",
     "tooltip": "Excluye correos genéricos que contengan 'agente', 'delta' o 'call' (cuentas compartidas o roles automáticos)."},
    {"id": "F5",  "bit": 2,  "group": "Correo",   "label": "Excluye correos hardcoded",
     "tooltip": "Excluye alejandroaguirre@habi.co, erickcastillo@tuhabi.mx, victorialechtig@tuhabi.mx."},
    {"id": "F6",  "bit": 3,  "group": "Correo",   "label": "Owners especiales req. contacto digital",
     "tooltip": "4 correos (lauracruz, alejandrobravo, juanquinones, juanarcos @habi.co) solo cuentan si el lead tiene contacto_digital diligenciado."},
    {"id": "F7",  "bit": 4,  "group": "Estado",   "label": "Estado: sin pricing incial",
     "tooltip": "Acepta deals con estado 'sin pricing incial' (con typo, estado 63). Grupo Estado funciona como OR: deal pasa si su estado coincide con al menos uno de los marcados."},
    {"id": "F8",  "bit": 5,  "group": "Estado",   "label": "Estado: no gestionado",
     "tooltip": "Acepta deals con estado 'no gestionado'. Grupo Estado funciona como OR."},
    {"id": "F9",  "bit": 6,  "group": "Estado",   "label": "Estado: cierre",
     "tooltip": "Acepta deals con estado 'cierre'. Grupo Estado funciona como OR."},
    {"id": "F10", "bit": 7,  "group": "Estado",   "label": "Estado: no hay suficientes datos",
     "tooltip": "Acepta deals con estado 'no hay suficientes datos para comparar'. Grupo Estado funciona como OR."},
    {"id": "F11", "bit": 8,  "group": "Calidad",  "label": "Calificación ≠ N/NH",
     "tooltip": "La calificación del lead no puede ser 'N' ni 'NH' (case-insensitive)."},
    {"id": "F12", "bit": 9,  "group": "Inmueble", "label": "check_a_pricing = 1",
     "tooltip": "El inmueble debe haber pasado por pricing (check_a_pricing = 1)."},
    {"id": "F13", "bit": 10, "group": "Inmueble", "label": "fecha_creacion no nula",
     "tooltip": "El inmueble debe tener fecha de creación registrada."},
    {"id": "F14", "bit": 11, "group": "Inmueble", "label": "nid no nulo",
     "tooltip": "El inmueble debe existir (nid no nulo). Redundante con join pero expuesto para coherencia con el doc."},
    {"id": "F15", "bit": 12, "group": "Inmo",     "label": "asignacion_descartes_top nula",
     "tooltip": "Excluye leads asignados solo al canal inmobiliaria (asignacion_descartes_top no nulo)."},
]


def main():
    if len(sys.argv) != 3:
        print("Usage: build_data.py <bq_query_output.json> <output_data.json>", file=sys.stderr)
        sys.exit(1)

    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    fuentes_seen = set()
    rows = []
    for r in raw:
        # BQ returns all fields as strings in JSON format.
        d = r["d"]
        m = int(r["m"])
        c = int(r["c"])
        f_ = r["f"]
        n = int(r["n"])
        fuentes_seen.add(f_)
        rows.append({"d": d, "m": m, "c": c, "f": f_, "n": n})

    # Canonical fuente order matches the reference doc; "Otro" last.
    fuente_order = ["Habimetro", "CRM", "Broker", "WEB", "Ventanas", "Leadform", "Otro"]
    fuentes_out = [x for x in fuente_order if x in fuentes_seen]

    rows.sort(key=lambda r: (r["d"], r["m"], r["c"], r["f"]))

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
        "country": "CO",
        "filters": FILTERS,
        "fuentes": fuentes_out,
        "rows": rows,
    }

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'), ensure_ascii=False)

    print(f"wrote {out_path}: {len(rows)} rows, {len(fuentes_out)} fuentes", file=sys.stderr)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x asignados-filtros/build_data.py
```

- [ ] **Step 3: Run the BQ query and pipe through the builder**

```bash
cd ~/habi/tableros-marketing
bq query --use_legacy_sql=false --format=json --max_rows=10000000 \
  < asignados-filtros/query.sql > /tmp/asignados-raw.json
python3 asignados-filtros/build_data.py /tmp/asignados-raw.json /tmp/data.json
```

Expected stderr output: `wrote /tmp/data.json: <N> rows, <M> fuentes`. N should be in 30k–150k range; M should be 5–7.

- [ ] **Step 4: Inspect data.json shape**

```bash
python3 -c "
import json
with open('/tmp/data.json') as f: d = json.load(f)
print('updated_at:', d['updated_at'])
print('country:', d['country'])
print('filters:', len(d['filters']))
print('fuentes:', d['fuentes'])
print('rows:', len(d['rows']))
print('first row:', d['rows'][0])
print('last row:', d['rows'][-1])
print('unique bitmasks:', len({r[\"m\"] for r in d['rows']}))
print('size MB:', round(__import__('os').path.getsize('/tmp/data.json') / 1024 / 1024, 2))
"
```

Expected:
- `filters: 13`
- `fuentes` ordered as the canonical list (subset based on actuals)
- `unique bitmasks` between 30 and 500
- `size MB` under 10 (ideally 1–5)

- [ ] **Step 5: Commit**

```bash
git add asignados-filtros/build_data.py
git commit -m "$(cat <<'EOF'
Asignados filtros: build script transforming BQ output to bitmask-indexed data.json

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: HTML skeleton + theme + data loader

**Files:**
- Create: `asignados-filtros/index.html`

- [ ] **Step 1: Write the skeleton with theme, back link, header, and JS data load**

```bash
cp /tmp/data.json asignados-filtros/data.json
```

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📢</text></svg>">
<title>Asignados — Explorador de filtros (CO)</title>
<style>
  :root {
    --bg: #0f172a;
    --card: #1e293b;
    --border: #334155;
    --accent: #818cf8;
    --accent-mart: #fbbf24;
    --text: #f8fafc;
    --text-secondary: #e2e8f0;
    --muted: #94a3b8;
    --bad: #f87171;
    --good: #4ade80;
  }
  * { box-sizing: border-box; }
  html, body { background: var(--bg); color: var(--text); margin: 0; padding: 0; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .back-link {
    display: inline-block; padding: 8px 12px; color: var(--muted);
    border: 1px solid var(--border); border-radius: 6px; margin: 12px;
  }
  .back-link:hover { color: var(--text); border-color: var(--accent); text-decoration: none; }
  .container { max-width: 1280px; margin: 0 auto; padding: 12px 24px 48px; }
  header.page { margin: 12px 0 18px; }
  header.page h1 { margin: 0 0 6px; font-size: 22px; }
  header.page p { margin: 0; color: var(--muted); font-size: 13px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 18px; }
  .card h2 { margin: 0 0 10px; font-size: 15px; font-weight: 600; color: var(--text-secondary); }
  /* hooks for next tasks; keep empty for now */
  .controls, .filter-panel, .chart-main, .breakdowns, .calificacion { /* layout in later tasks */ }
</style>
</head>
<body>
<a class="back-link" href="../">← Volver (Tableros Marketing Sellers)</a>
<div class="container">
  <header class="page">
    <h1>Leads asignados — Explorador de filtros (CO)</h1>
    <p id="header-meta">Cargando…</p>
  </header>

  <div class="card controls" id="controls"></div>
  <div class="card filter-panel" id="filter-panel"></div>
  <div class="card chart-main" id="chart-main"></div>
  <div class="card breakdowns" id="breakdowns"></div>
  <div class="card calificacion" id="calificacion"></div>
</div>

<script>
(async function () {
  const DATA_URL = 'data.json';
  const STATE_MASK = 240;      // bits 4..7 (F7..F10)
  const OTHER_MASK = 7951;     // bits 0..3, 8..12
  const ALL_ON     = 8191;     // all 13 toggleable bits set

  let DATA = null;

  async function loadData() {
    const res = await fetch(DATA_URL, { cache: 'no-store' });
    if (!res.ok) throw new Error('No pude cargar data.json: ' + res.status);
    DATA = await res.json();
  }

  function setMeta() {
    const el = document.getElementById('header-meta');
    const dt = new Date(DATA.updated_at);
    el.textContent = `Actualizado ${dt.toLocaleString('es-CO')} · ${DATA.rows.length.toLocaleString('es-CO')} filas · ${DATA.fuentes.length} fuentes`;
  }

  try {
    await loadData();
    setMeta();
    // Hooks for next tasks:
    window.__DATA__ = DATA;
    window.__MASKS__ = { STATE_MASK, OTHER_MASK, ALL_ON };
  } catch (e) {
    document.getElementById('header-meta').textContent = 'Error: ' + e.message;
    console.error(e);
  }
})();
</script>

</body>
</html>
```

- [ ] **Step 2: Open it in a browser and verify**

```bash
cd ~/habi/tableros-marketing/asignados-filtros
python3 -m http.server 8765 &
sleep 1
echo "Open http://localhost:8765/ in browser"
```

Expected in browser:
- Header "Leads asignados — Explorador de filtros (CO)"
- Meta line "Actualizado ... · N filas · M fuentes" with non-zero numbers
- Five empty `card` divs visible
- Stop the server when done: `kill %1` (or `fg` + Ctrl-C)

- [ ] **Step 3: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignados-filtros/index.html asignados-filtros/data.json
git commit -m "$(cat <<'EOF'
Asignados filtros: HTML skeleton with theme, back link, and data loader

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Filter panel (16 toggles with locks)

**Files:**
- Modify: `asignados-filtros/index.html`

- [ ] **Step 1: Add filter panel styles**

Inside the existing `<style>` block, before the closing `</style>`, append:

```css
.filter-groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
.filter-group h3 { margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.filter-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
.filter-row input[type=checkbox] { width: 16px; height: 16px; accent-color: var(--accent); }
.filter-row .lock { color: var(--muted); font-size: 11px; }
.filter-row .info { color: var(--muted); cursor: help; }
.filter-row.locked { opacity: 0.7; }
.warn-banner { background: rgba(248, 113, 113, 0.12); border: 1px solid var(--bad); color: var(--bad); padding: 8px 12px; border-radius: 6px; margin-bottom: 12px; font-size: 13px; display: none; }
.warn-banner.show { display: block; }
.controls-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.chip-group { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.chip { padding: 6px 12px; cursor: pointer; background: transparent; color: var(--text-secondary); border: 0; font-size: 13px; }
.chip.active { background: var(--accent); color: #0b1224; font-weight: 600; }
.chip + .chip { border-left: 1px solid var(--border); }
.btn { padding: 6px 12px; border: 1px solid var(--border); border-radius: 6px; background: transparent; color: var(--text-secondary); cursor: pointer; font-size: 13px; }
.btn:hover { border-color: var(--accent); color: var(--text); }
```

- [ ] **Step 2: Inside the `<script>` block, before the IIFE ends, add the filter state and rendering**

Replace the script block with this expanded version (keep the existing constants and `loadData`/`setMeta` functions):

```html
<script>
(async function () {
  const DATA_URL = 'data.json';
  const STATE_MASK = 240;
  const OTHER_MASK = 7951;
  const ALL_ON     = 8191;
  const STATE_BITS = [4, 5, 6, 7];  // F7..F10

  let DATA = null;
  // user state — which filters are active (true = applied). Defaults to all on (= mart oficial).
  const state = {
    granularity: 'week',     // 'day' | 'week' | 'month'
    showMart: true,
    active: {},              // { F3: true, ..., F15: true }
  };

  function userBitmask() {
    let m = 0;
    for (const f of DATA.filters) {
      if (state.active[f.id]) m |= (1 << f.bit);
    }
    return m;
  }

  function isStateGroupActive(req) {
    return (req & STATE_MASK) !== 0;
  }

  async function loadData() {
    const res = await fetch(DATA_URL, { cache: 'no-store' });
    if (!res.ok) throw new Error('No pude cargar data.json: ' + res.status);
    DATA = await res.json();
    // Default state: all filters on
    for (const f of DATA.filters) state.active[f.id] = true;
  }

  function setMeta() {
    const el = document.getElementById('header-meta');
    const dt = new Date(DATA.updated_at);
    el.textContent = `Actualizado ${dt.toLocaleString('es-CO')} · ${DATA.rows.length.toLocaleString('es-CO')} filas · ${DATA.fuentes.length} fuentes`;
  }

  function renderControls() {
    const el = document.getElementById('controls');
    el.innerHTML = `
      <h2>Granularidad y atajos</h2>
      <div class="controls-row">
        <div class="chip-group" id="granularity">
          <button class="chip" data-g="day">Día</button>
          <button class="chip active" data-g="week">Semana</button>
          <button class="chip" data-g="month">Mes</button>
        </div>
        <label class="filter-row" style="margin-left:8px;">
          <input type="checkbox" id="toggle-mart" ${state.showMart ? 'checked' : ''}/>
          Mostrar línea mart oficial
        </label>
        <button class="btn" data-action="all-on">Todos on (mart)</button>
        <button class="btn" data-action="all-off">Todos off (universo crudo)</button>
        <button class="btn" data-action="reset">Reset</button>
      </div>
    `;
    el.querySelectorAll('[data-g]').forEach(btn => {
      btn.addEventListener('click', () => {
        state.granularity = btn.dataset.g;
        el.querySelectorAll('[data-g]').forEach(b => b.classList.toggle('active', b === btn));
        renderAll();
      });
    });
    el.querySelector('#toggle-mart').addEventListener('change', e => {
      state.showMart = e.target.checked;
      renderAll();
    });
    el.querySelector('[data-action="all-on"]').addEventListener('click', () => {
      for (const f of DATA.filters) state.active[f.id] = true;
      renderAll();
    });
    el.querySelector('[data-action="all-off"]').addEventListener('click', () => {
      for (const f of DATA.filters) state.active[f.id] = false;
      renderAll();
    });
    el.querySelector('[data-action="reset"]').addEventListener('click', () => {
      for (const f of DATA.filters) state.active[f.id] = true;
      state.granularity = 'week';
      state.showMart = true;
      renderAll();
    });
  }

  function renderFilterPanel() {
    const el = document.getElementById('filter-panel');
    const byGroup = {};
    for (const f of DATA.filters) {
      (byGroup[f.group] = byGroup[f.group] || []).push(f);
    }
    const lockedRows = `
      <div class="filter-group">
        <h3>Origen</h3>
        <div class="filter-row locked"><span class="lock">🔒</span> F1 · Solo cambios de hubspot_owner_id <span class="info" title="Fuente: history WHERE propiedad='hubspot_owner_id'. Sin este filtro no hay universo de asignaciones.">ℹ︎</span></div>
        <div class="filter-row locked"><span class="lock">🔒</span> F2 · Primera asignación por nid <span class="info" title="QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY fecha) = 1. Convención del mart.">ℹ︎</span></div>
      </div>
    `;
    const fechaRow = `
      <div class="filter-group">
        <h3>Fecha</h3>
        <div class="filter-row locked"><span class="lock">🔒</span> F16 · UTC → Colombia (UTC-5) <span class="info" title="DATE_SUB(fecha, INTERVAL 5 HOUR). Transversal a todos los reportes.">ℹ︎</span></div>
      </div>
    `;
    const groupsOrder = ['Correo', 'Estado', 'Calidad', 'Inmueble', 'Inmo'];
    const groupsHtml = groupsOrder.map(g => {
      const rows = (byGroup[g] || []).map(f => `
        <label class="filter-row" data-fid="${f.id}">
          <input type="checkbox" data-fid="${f.id}" ${state.active[f.id] ? 'checked' : ''}/>
          ${f.id} · ${f.label}
          <span class="info" title="${f.tooltip.replace(/"/g,'&quot;')}">ℹ︎</span>
        </label>
      `).join('');
      return `<div class="filter-group"><h3>${g}</h3>${rows}</div>`;
    }).join('');

    el.innerHTML = `
      <h2>Filtros</h2>
      <div class="warn-banner" id="state-warn">⚠ Los 4 estados (F7–F10) están apagados — el universo será 0. Activá al menos uno para ver datos.</div>
      <div class="filter-groups">
        ${lockedRows}
        ${groupsHtml}
        ${fechaRow}
      </div>
    `;
    el.querySelectorAll('input[type=checkbox][data-fid]').forEach(cb => {
      cb.addEventListener('change', () => {
        state.active[cb.dataset.fid] = cb.checked;
        renderAll();
      });
    });
    updateStateWarn();
  }

  function updateStateWarn() {
    const req = userBitmask();
    const warn = document.getElementById('state-warn');
    if (!warn) return;
    warn.classList.toggle('show', !isStateGroupActive(req));
  }

  // Renderers for next tasks — stubs for now
  function renderChartMain()    { document.getElementById('chart-main').innerHTML = '<h2>Chart principal</h2><div class="muted">Pendiente Task 5</div>'; }
  function renderBreakdowns()   { document.getElementById('breakdowns').innerHTML = '<h2>Breakdowns por filtro</h2><div class="muted">Pendiente Task 6</div>'; }
  function renderCalificacion() { document.getElementById('calificacion').innerHTML = '<h2>Calificación</h2><div class="muted">Pendiente Task 7</div>'; }

  function renderAll() {
    updateStateWarn();
    renderChartMain();
    renderBreakdowns();
    renderCalificacion();
  }

  try {
    await loadData();
    setMeta();
    renderControls();
    renderFilterPanel();
    renderAll();
    window.__DATA__ = DATA;
    window.__STATE__ = state;
  } catch (e) {
    document.getElementById('header-meta').textContent = 'Error: ' + e.message;
    console.error(e);
  }
})();
</script>
```

- [ ] **Step 2: Reload the browser at http://localhost:8765/**

Expected:
- Controls bar with granularity chips (Semana active), mart toggle checked, three buttons
- Filter panel with all 16 entries: F1/F2/F16 with lock icons, F3..F15 as checkboxes (all checked by default)
- Tooltips show on hover over the ℹ︎ icons
- Uncheck all 4 state filters → red warning banner appears
- Re-check at least one → warning disappears

- [ ] **Step 3: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignados-filtros/index.html
git commit -m "$(cat <<'EOF'
Asignados filtros: controls bar and filter panel with locks and state-group warning

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Main chart with two lines

**Files:**
- Modify: `asignados-filtros/index.html`

- [ ] **Step 1: Add helper functions for period bucketing and querying**

In the `<script>` IIFE, before `renderControls`, add these helpers:

```js
// --- Period bucketing ---
function isoMonday(dateStr) {
  // dateStr 'YYYY-MM-DD' → 'YYYY-MM-DD' of Monday of that ISO week
  const d = new Date(dateStr + 'T00:00:00Z');
  const day = d.getUTCDay() || 7;  // Sunday=7
  d.setUTCDate(d.getUTCDate() - day + 1);
  return d.toISOString().slice(0, 10);
}
function monthStart(dateStr) {
  return dateStr.slice(0, 7) + '-01';
}
function bucket(dateStr) {
  if (state.granularity === 'day') return dateStr;
  if (state.granularity === 'week') return isoMonday(dateStr);
  return monthStart(dateStr);
}
function bucketLabel(b) {
  if (state.granularity === 'day') return b;
  if (state.granularity === 'week') return 'Sem ' + b.slice(5);  // MM-DD
  // month
  const [y, m] = b.split('-');
  return ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'][parseInt(m,10)-1] + ' ' + y.slice(2);
}
function currentBucketIsPartial(b) {
  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);
  if (state.granularity === 'day') return b === todayStr;
  if (state.granularity === 'week') return b === isoMonday(todayStr);
  return b === monthStart(todayStr);
}

// --- Filter evaluation ---
function rowPassesUser(row, reqOther, reqState) {
  if ((row.m & reqOther) !== reqOther) return false;
  if (reqState === 0) return false;  // degenerate: no states allowed
  if ((row.m & reqState) === 0) return false;
  return true;
}
function rowPassesMart(row) {
  // ALL_ON = 8191; OTHER part = 7951, STATE part = 240, requires at least one state bit
  return (row.m & 7951) === 7951 && (row.m & 240) !== 0;
}

// --- Aggregation: returns Map<bucket, count> ---
function aggregateUser(rowFilter) {
  const req = userBitmask();
  const reqOther = req & OTHER_MASK;
  const reqState = req & STATE_MASK;
  const out = new Map();
  for (const r of DATA.rows) {
    if (rowFilter && !rowFilter(r)) continue;
    if (!rowPassesUser(r, reqOther, reqState)) continue;
    const b = bucket(r.d);
    out.set(b, (out.get(b) || 0) + r.n);
  }
  return out;
}
function aggregateMart(rowFilter) {
  const out = new Map();
  for (const r of DATA.rows) {
    if (rowFilter && !rowFilter(r)) continue;
    if (!rowPassesMart(r)) continue;
    const b = bucket(r.d);
    out.set(b, (out.get(b) || 0) + r.n);
  }
  return out;
}

// --- Build last 18 periods (excluding current incomplete) ---
function lastNBuckets(n) {
  const seen = new Set();
  for (const r of DATA.rows) seen.add(bucket(r.d));
  const all = [...seen].sort();
  const completed = all.filter(b => !currentBucketIsPartial(b));
  return completed.slice(-n);
}
```

- [ ] **Step 2: Add chart styles**

Append to the `<style>` block:

```css
.chart-svg { width: 100%; height: 320px; display: block; }
.chart-legend { display: flex; gap: 18px; font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.chart-legend .swatch { display: inline-block; width: 12px; height: 3px; vertical-align: middle; margin-right: 5px; }
.chart-tip { position: absolute; pointer-events: none; background: #0b1224; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 12px; display: none; z-index: 10; }
.chart-host { position: relative; }
.muted { color: var(--muted); }
```

- [ ] **Step 3: Implement `renderChartMain` (replace the stub)**

Replace the `renderChartMain` stub with:

```js
function renderChartMain() {
  const el = document.getElementById('chart-main');
  const buckets = lastNBuckets(18);
  const user = aggregateUser();
  const mart = aggregateMart();

  const userSeries = buckets.map(b => user.get(b) || 0);
  const martSeries = buckets.map(b => mart.get(b) || 0);

  const maxY = Math.max(1, ...userSeries, ...martSeries);
  const W = 1180, H = 320, padL = 50, padR = 12, padT = 16, padB = 36;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const x = i => padL + (buckets.length === 1 ? innerW/2 : (i * innerW / (buckets.length - 1)));
  const y = v => padT + innerH - (v / maxY) * innerH;

  const userPath = userSeries.map((v, i) => (i ? 'L' : 'M') + x(i) + ',' + y(v)).join(' ');
  const martPath = martSeries.map((v, i) => (i ? 'L' : 'M') + x(i) + ',' + y(v)).join(' ');

  const yTicks = 5;
  const yTickEls = [];
  for (let i = 0; i <= yTicks; i++) {
    const v = Math.round((maxY * i) / yTicks);
    const yy = y(v);
    yTickEls.push(`<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="#1f2a44" stroke-width="1"/>`);
    yTickEls.push(`<text x="${padL - 6}" y="${yy + 4}" text-anchor="end" font-size="11" fill="#94a3b8">${v.toLocaleString('es-CO')}</text>`);
  }
  const xTickEvery = buckets.length > 12 ? 3 : 2;
  const xTickEls = buckets.map((b, i) => {
    if (i % xTickEvery !== 0 && i !== buckets.length - 1) return '';
    return `<text x="${x(i)}" y="${H - padB + 18}" text-anchor="middle" font-size="11" fill="#94a3b8">${bucketLabel(b)}</text>`;
  }).join('');

  const lastIdx = buckets.length - 1;
  const lastUser = userSeries[lastIdx] || 0;
  const lastMart = martSeries[lastIdx] || 0;

  el.innerHTML = `
    <h2>Universo de asignados</h2>
    <div class="chart-legend">
      <span><span class="swatch" style="background:${getComputedStyle(document.documentElement).getPropertyValue('--accent')};"></span>Usuario · último período: <strong>${lastUser.toLocaleString('es-CO')}</strong></span>
      ${state.showMart ? `<span><span class="swatch" style="background:${getComputedStyle(document.documentElement).getPropertyValue('--accent-mart')};border-top:1px dashed ${getComputedStyle(document.documentElement).getPropertyValue('--accent-mart')};"></span>Mart oficial · último: <strong>${lastMart.toLocaleString('es-CO')}</strong></span>` : ''}
      <span>Δ usuario vs mart: <strong>${(lastUser - lastMart).toLocaleString('es-CO')}</strong> (${lastMart ? Math.round((lastUser - lastMart) / lastMart * 100) : 0}%)</span>
    </div>
    <div class="chart-host">
      <svg class="chart-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        ${yTickEls.join('')}
        ${state.showMart ? `<path d="${martPath}" stroke="var(--accent-mart)" stroke-width="1.6" fill="none" stroke-dasharray="6 4"/>` : ''}
        <path d="${userPath}" stroke="var(--accent)" stroke-width="2.2" fill="none"/>
        <circle cx="${x(lastIdx)}" cy="${y(lastUser)}" r="4" fill="var(--accent)"/>
        ${state.showMart ? `<circle cx="${x(lastIdx)}" cy="${y(lastMart)}" r="3" fill="var(--accent-mart)"/>` : ''}
        ${xTickEls}
      </svg>
    </div>
  `;
}
```

- [ ] **Step 4: Reload and verify**

Expected in browser:
- Chart appears with 18 weekly periods (default)
- With "all on": índigo line and ámbar dashed line overlap (≈ same values) — small drift OK
- Click "Todos off (universo crudo)" → índigo line jumps up to ~1.5-2x the mart line
- Toggle a single filter (e.g. uncheck F12) and observe the user line change while mart stays
- Switch granularity to Día → 18 daily points; Mes → 18 monthly points

- [ ] **Step 5: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignados-filtros/index.html
git commit -m "$(cat <<'EOF'
Asignados filtros: main chart with user vs mart lines and granularity selector

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Breakdowns table with marginal effects

**Files:**
- Modify: `asignados-filtros/index.html`

- [ ] **Step 1: Add table styles**

Append to the `<style>` block:

```css
table.breakdowns-table { width: 100%; border-collapse: collapse; font-size: 13px; }
table.breakdowns-table th, table.breakdowns-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }
table.breakdowns-table th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
table.breakdowns-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
table.breakdowns-table tr.row-toggle:hover { background: rgba(129, 140, 248, 0.07); cursor: pointer; }
table.breakdowns-table tr.row-toggle.off td:first-child { opacity: 0.55; }
.signed-down { color: var(--bad); }
.signed-up   { color: var(--good); }
```

- [ ] **Step 2: Replace the `renderBreakdowns` stub**

```js
function renderBreakdowns() {
  const el = document.getElementById('breakdowns');
  const buckets = lastNBuckets(18);
  if (buckets.length === 0) {
    el.innerHTML = '<h2>Breakdowns por filtro</h2><div class="muted">Sin datos</div>';
    return;
  }
  const lastBucket = buckets[buckets.length - 1];
  const prevBucket = buckets.length > 1 ? buckets[buckets.length - 2] : null;

  // Count for the user's current set, restricted to a specific bucket.
  function countWith(activeOverrides, bucketKey) {
    const req = (() => {
      let m = 0;
      for (const f of DATA.filters) {
        const v = (f.id in activeOverrides) ? activeOverrides[f.id] : state.active[f.id];
        if (v) m |= (1 << f.bit);
      }
      return m;
    })();
    const reqOther = req & OTHER_MASK;
    const reqState = req & STATE_MASK;
    let total = 0;
    for (const r of DATA.rows) {
      if (bucket(r.d) !== bucketKey) continue;
      if ((r.m & reqOther) !== reqOther) continue;
      if (reqState === 0) continue;
      if ((r.m & reqState) === 0) continue;
      total += r.n;
    }
    return total;
  }

  const baseCurrent = countWith({}, lastBucket);
  const basePrev    = prevBucket ? countWith({}, prevBucket) : null;

  const rowsHtml = DATA.filters.map(f => {
    const isOn = !!state.active[f.id];
    // Marginal effect: difference in current bucket from flipping this filter.
    const flipped = countWith({ [f.id]: !isOn }, lastBucket);
    const delta = flipped - baseCurrent;
    const sign = delta >= 0 ? 'up' : 'down';
    const arrow = delta >= 0 ? '↑ agrega' : '↓ quita';
    const deltaTxt = `${arrow} ${Math.abs(delta).toLocaleString('es-CO')}`;
    return `
      <tr class="row-toggle ${isOn ? '' : 'off'}" data-fid="${f.id}">
        <td>${f.id} · ${f.label}</td>
        <td>${f.group}</td>
        <td>${isOn ? '✓ activo' : '○ apagado'}</td>
        <td class="num">${baseCurrent.toLocaleString('es-CO')}</td>
        <td class="num signed-${sign}">${deltaTxt}</td>
        <td class="num muted">${basePrev !== null ? basePrev.toLocaleString('es-CO') : '—'}</td>
      </tr>
    `;
  }).join('');

  el.innerHTML = `
    <h2>Efecto de cada filtro · período actual = ${bucketLabel(lastBucket)}</h2>
    <table class="breakdowns-table">
      <thead>
        <tr>
          <th>Filtro</th>
          <th>Grupo</th>
          <th>Estado</th>
          <th class="num">Universo actual</th>
          <th class="num">Si lo invierto</th>
          <th class="num">Período anterior</th>
        </tr>
      </thead>
      <tbody>${rowsHtml}</tbody>
    </table>
  `;
  el.querySelectorAll('tr.row-toggle').forEach(tr => {
    tr.addEventListener('click', () => {
      const fid = tr.dataset.fid;
      state.active[fid] = !state.active[fid];
      // sync checkbox in panel
      const cb = document.querySelector(`input[type=checkbox][data-fid="${fid}"]`);
      if (cb) cb.checked = state.active[fid];
      renderAll();
    });
  });
}
```

- [ ] **Step 3: Reload and verify**

Expected:
- Table shows 13 rows, one per toggleable filter
- "Universo actual" is the same value for all rows (= total con configuración actual)
- "Si lo invierto" shows the delta of toggling that single filter (↑ green positive, ↓ red negative)
- Clicking a row toggles the corresponding filter and the chart + table refresh
- Filter checkboxes stay in sync with row state

- [ ] **Step 4: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignados-filtros/index.html
git commit -m "$(cat <<'EOF'
Asignados filtros: breakdowns table with marginal effect per filter

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Calificación block

**Files:**
- Modify: `asignados-filtros/index.html`

- [ ] **Step 1: Add styles for the small charts**

Append to the `<style>` block:

```css
.cali-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.cali-card { background: rgba(15, 23, 42, 0.4); border: 1px solid var(--border); border-radius: 8px; padding: 10px; }
.cali-card h3 { margin: 0 0 8px; font-size: 13px; color: var(--text-secondary); }
.cali-card .summary { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.cali-card svg { width: 100%; height: 160px; display: block; }
@media (max-width: 720px) { .cali-grid { grid-template-columns: 1fr; } }
```

- [ ] **Step 2: Add a generic mini-chart helper and the `renderCalificacion` implementation**

Replace the `renderCalificacion` stub with:

```js
function miniLineSvg(seriesA, seriesB, opts) {
  const W = 560, H = 160, padL = 36, padR = 10, padT = 8, padB = 22;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const maxY = Math.max(1, ...seriesA, ...(opts.compare ? seriesB : []));
  const xs = i => padL + (seriesA.length <= 1 ? innerW/2 : i * innerW / (seriesA.length - 1));
  const ys = v => padT + innerH - (v / maxY) * innerH;
  const pathA = seriesA.map((v, i) => (i ? 'L' : 'M') + xs(i) + ',' + ys(v)).join(' ');
  const pathB = opts.compare ? seriesB.map((v, i) => (i ? 'L' : 'M') + xs(i) + ',' + ys(v)).join(' ') : '';
  const yTicks = 3;
  let ticks = '';
  for (let i = 0; i <= yTicks; i++) {
    const v = (maxY * i) / yTicks;
    const yy = ys(v);
    const label = opts.percent ? Math.round(v * 100) + '%' : Math.round(v).toLocaleString('es-CO');
    ticks += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="#1f2a44"/>`;
    ticks += `<text x="${padL - 4}" y="${yy + 4}" text-anchor="end" font-size="10" fill="#94a3b8">${label}</text>`;
  }
  const lastIdx = seriesA.length - 1;
  return `
    <svg viewBox="0 0 ${W} ${H}">
      ${ticks}
      ${opts.compare ? `<path d="${pathB}" stroke="var(--accent-mart)" stroke-width="1.4" fill="none" stroke-dasharray="5 3"/>` : ''}
      <path d="${pathA}" stroke="var(--accent)" stroke-width="2" fill="none"/>
      ${lastIdx >= 0 ? `<circle cx="${xs(lastIdx)}" cy="${ys(seriesA[lastIdx])}" r="3.5" fill="var(--accent)"/>` : ''}
    </svg>
  `;
}

function renderCalificacion() {
  const el = document.getElementById('calificacion');
  const buckets = lastNBuckets(18);
  if (buckets.length === 0) {
    el.innerHTML = '<h2>Calificación</h2><div class="muted">Sin datos</div>';
    return;
  }
  const userCal = aggregateUser(r => r.c === 1);
  const userAll = aggregateUser();
  const martCal = aggregateMart(r => r.c === 1);
  const martAll = aggregateMart();

  const calA = buckets.map(b => userCal.get(b) || 0);
  const calB = buckets.map(b => martCal.get(b) || 0);
  const rateA = buckets.map(b => {
    const tot = userAll.get(b) || 0;
    return tot ? (userCal.get(b) || 0) / tot : 0;
  });
  const rateB = buckets.map(b => {
    const tot = martAll.get(b) || 0;
    return tot ? (martCal.get(b) || 0) / tot : 0;
  });

  const lastCalUser = calA[calA.length - 1] || 0;
  const lastRateUser = rateA[rateA.length - 1] || 0;
  const lastCalMart = calB[calB.length - 1] || 0;
  const lastRateMart = rateB[rateB.length - 1] || 0;

  el.innerHTML = `
    <h2>Calificación (state_id IN 20, 63)</h2>
    <div class="cali-grid">
      <div class="cali-card">
        <h3>Calificados · volumen</h3>
        <div class="summary">Usuario último: <strong>${lastCalUser.toLocaleString('es-CO')}</strong> · Mart último: <strong>${lastCalMart.toLocaleString('es-CO')}</strong></div>
        ${miniLineSvg(calA, calB, { compare: state.showMart, percent: false })}
      </div>
      <div class="cali-card">
        <h3>Tasa de calificación · % del universo</h3>
        <div class="summary">Usuario último: <strong>${(lastRateUser*100).toFixed(1)}%</strong> · Mart último: <strong>${(lastRateMart*100).toFixed(1)}%</strong></div>
        ${miniLineSvg(rateA, rateB, { compare: state.showMart, percent: true })}
      </div>
    </div>
  `;
}
```

- [ ] **Step 3: Reload and verify**

Expected:
- Two mini-charts side by side: "Calificados · volumen" and "Tasa de calificación · %"
- Both show 18 weekly periods (default)
- Toggle a filter and the user (índigo) line in both charts updates; mart (ámbar dashed) stays
- Tasa should usually be 20–60% in CO
- "Mostrar línea mart oficial" toggle hides/shows the ámbar line in both mini-charts and in the main chart

- [ ] **Step 4: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignados-filtros/index.html
git commit -m "$(cat <<'EOF'
Asignados filtros: calificación block with volume and rate mini-charts

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Landing card + workflow integration

**Files:**
- Modify: `index.html` (root)
- Modify: `.github/workflows/update-data.yml`

- [ ] **Step 1: Inspect the current landing**

```bash
cd ~/habi/tableros-marketing
grep -n 'class="card"' index.html | head -20
```

Expected: a list of `<a class="card">` entries, one per existing tablero. Pick a spot to insert the new one (typically end of the same `<div>`, or alphabetical).

- [ ] **Step 2: Add the new card**

Open `~/habi/tableros-marketing/index.html`. Locate a `<a class="card" ...>` block that links to e.g. `wbr-2-0/` and insert a sibling block:

```html
<a class="card" href="asignados-filtros/">
  <h3>Asignados · Explorador de filtros (CO)</h3>
  <p>Toggleá cada uno de los 16 filtros del WBR mart para ver cómo cambia el universo de asignados.</p>
</a>
```

Match the surrounding indentation and structure of neighbouring cards.

- [ ] **Step 3: Verify the landing**

```bash
cd ~/habi/tableros-marketing
python3 -m http.server 8765 &
sleep 1
echo "Open http://localhost:8765/ — card should appear"
```

Click the new card → should land on the new tablero at `http://localhost:8765/asignados-filtros/`. Stop the server with `kill %1`.

- [ ] **Step 4: Add workflow steps**

Open `.github/workflows/update-data.yml`. Find the last `bq query ... > .../data.json` step and add two new steps after it (and BEFORE the "Commit and push" step at the bottom). Use this exact block, adjusting only the YAML indentation to match the existing file:

```yaml
      - name: Query BigQuery — asignados filtros (CO)
        if: always()
        run: |
          bq query --use_legacy_sql=false --format=json --max_rows=10000000 \
            < asignados-filtros/query.sql > /tmp/asignados-raw.json

      - name: Build asignados-filtros/data.json
        if: always()
        run: |
          python3 asignados-filtros/build_data.py /tmp/asignados-raw.json asignados-filtros/data.json
```

Then locate the commit step (usually a single `git add` + `git commit` block). Add `asignados-filtros/data.json` to the `git add` line. Example before/after:

Before:
```yaml
          git add wbr-2-0/data.json marketing-wbr/data.json okr-marketing/data.json incompletos-colombia/data.json
```

After:
```yaml
          git add wbr-2-0/data.json marketing-wbr/data.json okr-marketing/data.json incompletos-colombia/data.json asignados-filtros/data.json
```

(Use the actual list of paths currently in the file; just append `asignados-filtros/data.json` to it.)

- [ ] **Step 5: Dry-run the workflow locally**

```bash
cd ~/habi/tableros-marketing
bq query --use_legacy_sql=false --format=json --max_rows=10000000 \
  < asignados-filtros/query.sql > /tmp/asignados-raw.json
python3 asignados-filtros/build_data.py /tmp/asignados-raw.json asignados-filtros/data.json
ls -la asignados-filtros/data.json
```

Expected: `data.json` exists, non-zero size (1–10 MB).

- [ ] **Step 6: Commit and push**

```bash
cd ~/habi/tableros-marketing
git add index.html .github/workflows/update-data.yml asignados-filtros/data.json
git commit -m "$(cat <<'EOF'
Asignados filtros: hub card and consolidated workflow integration

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin main
```

- [ ] **Step 7: Verify deploy**

Wait ~30s for GH Pages to pick up the push.

```bash
sleep 30
curl -sI https://camilootoya-habi.github.io/tableros-marketing-habi/asignados-filtros/ | head -1
```

Expected: `HTTP/2 200`.

Open https://camilootoya-habi.github.io/tableros-marketing-habi/asignados-filtros/ in a browser and re-verify:
- Header, controls, filter panel render
- Chart shows recent data
- Toggle a filter, see it change
- Breakdowns table reacts
- Calificación block shows both mini-charts

- [ ] **Step 8: Trigger the workflow manually to confirm auto-update works**

```bash
gh workflow run update-data.yml -R camotoya/tableros-marketing-habi
sleep 5
gh run list -R camotoya/tableros-marketing-habi --workflow update-data.yml --limit 1
```

Watch the run until it completes (`gh run watch -R camotoya/tableros-marketing-habi`). Expected: success. After it finishes, the auto-commit should include `asignados-filtros/data.json` with fresh `updated_at`.

---

## Acceptance checklist (from spec)

After all tasks complete, verify against the success criteria of the spec:

- [ ] Tablero publicado en GH Pages y actualizándose diario (workflow ran green at least once with this step included)
- [ ] Con "Todos on" la línea índigo coincide (≤ ±1%) con la ámbar (mart oficial)
- [ ] Con "Todos off" el universo es mayor que el mart oficial — diferencia consistente con el doc (~1k nids/mes en el período post-abril-2026)
- [ ] El conteo del mart oficial en el último período del chart coincide con un query directo al mart (validación cruzada)
- [ ] Time to interactive < 2s en conexión normal; toggle de filtro < 100ms

---

## Notes for the implementer

- The repo has **no test framework** by convention; verification is data inspection + browser checks. Do NOT introduce a test framework for this tablero.
- Vanilla JS only — do NOT add bundlers, frameworks, npm packages.
- All Python is **stdlib-only** — do NOT add `requirements.txt` or pip installs.
- The theme variables and overall card pattern come from `wbr-2-0/index.html` and `marketing-wbr/index.html`; refer to those if styling questions come up. Avoid premature abstraction (no shared CSS file).
- Commit messages stay short and imperative; never use "Auto-update" prefix (reserved for the bot).
- The BQ query targets `papyrus-master.src_sellers_hubspot.history` which is large (~5M rows). The `WHERE propiedad='hubspot_owner_id'` plus 540-day window should keep scan under 1 GB. If the workflow times out, check the query plan in BQ first before optimizing further.
