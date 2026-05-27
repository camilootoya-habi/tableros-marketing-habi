# Marketing WBR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Marketing WBR dashboard (Block 1: Dupont matrix) for CO, hooked into the consolidated auto-update workflow and added to the hub.

**Architecture:** Static dashboard following the same pattern as existing tableros (`okr-marketing`, `incompletos-direccion`): two SQL queries against BigQuery → Python builder script → compact `data.json` → vanilla JS front-end that aggregates per window in the browser. Auto-updates daily via a single consolidated GitHub Actions workflow.

**Tech Stack:** BigQuery (SQL), Python 3 (stdlib only), vanilla HTML/CSS/JS (no framework, no build step), GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-05-04-marketing-wbr-design.md`

**Repo conventions to follow:**
- Working directory: `~/habi/tableros-marketing/`
- Subfolder: `marketing-wbr/`
- Theme variables, favicon, back-link, theme toggle: copy from `okr-marketing/index.html`
- Workflow: `.github/workflows/update-data.yml` (consolidated)
- Commits: imperative English, no `Auto-update` prefix (those are bot-only). Include `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer.

---

## File Structure

```
marketing-wbr/
├── query_leads.sql       ← leads + calificados aggregated by (day, channel)
├── query_spend.sql       ← spend by (day, channel) via UTM dict join
├── build_data.py         ← merge two BQ JSON outputs → compact data.json
├── data.json             ← auto-generated; committed by workflow
└── index.html            ← UI: selectors, matrix, color logic, theme toggle
```

Modified files outside `marketing-wbr/`:
- `index.html` (root): add card linking to the new dashboard
- `.github/workflows/update-data.yml`: add 3 new steps (query_leads, query_spend, build) + add `marketing-wbr/data.json` to commit step

---

## Task 1: Skeleton + leads query

**Files:**
- Create: `marketing-wbr/query_leads.sql`

- [ ] **Step 1: Create the folder**

```bash
cd ~/habi/tableros-marketing
mkdir -p marketing-wbr
```

- [ ] **Step 2: Write the leads query**

Create `marketing-wbr/query_leads.sql` with this exact content:

```sql
-- Marketing WBR — leads + calificados (CO)
-- Output: one row per (dia, channel) with reg + cal counts.
-- Window: last 180 days, excludes today.
-- Channel logic: UTM mkt_channel_medium, fallback "{fuente} Direct" when no campaign.

WITH utm_dedup AS (
  SELECT *
  FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
  QUALIFY ROW_NUMBER() OVER(PARTITION BY campana_mercadeo_original ORDER BY campana_mercadeo_original) = 1
),

leads AS (
  SELECT
    g.negocio_id,
    DATE(g.fecha_creacion) AS dia,
    CASE
      WHEN g.campana_mercadeo IS NULL OR g.campana_mercadeo = ''
        THEN CONCAT(g.fuente, ' Direct')
      WHEN m.mkt_channel_medium IS NULL OR m.mkt_channel_medium = ''
        THEN g.campana_mercadeo
      ELSE m.mkt_channel_medium
    END AS channel
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g
  LEFT JOIN utm_dedup m ON g.campana_mercadeo = m.campana_mercadeo_original
  WHERE g.fuente_id IN (3, 7, 20, 35, 39, 47)
    AND DATE(g.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
    AND DATE(g.fecha_creacion) < CURRENT_DATE()
),

cal AS (
  SELECT negocio_id, MIN(fecha_actualizacion) AS cal_ts
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
  WHERE estado_id IN (20, 63)
  GROUP BY 1
)

SELECT
  CAST(l.dia AS STRING) AS dia,
  l.channel,
  COUNT(*) AS reg,
  COUNTIF(c.cal_ts IS NOT NULL) AS cal
FROM leads l
LEFT JOIN cal c ON c.negocio_id = l.negocio_id
GROUP BY 1, 2
ORDER BY 1, 2
```

- [ ] **Step 3: Run the query against BigQuery and save to /tmp**

Run:

```bash
bq --project_id=papyrus-data query --use_legacy_sql=false --format=json --max_rows=200000 < marketing-wbr/query_leads.sql > /tmp/wbr_leads_co.json
```

Expected: command exits 0, file is non-empty.

- [ ] **Step 4: Validate the output shape**

Run:

```bash
python3 -c "
import json
data = json.load(open('/tmp/wbr_leads_co.json'))
print(f'rows: {len(data)}')
print(f'sample: {data[0]}')
days = sorted({r[\"dia\"] for r in data})
channels = sorted({r[\"channel\"] for r in data})
print(f'days: {len(days)} ({days[0]} → {days[-1]})')
print(f'channels: {len(channels)}')
print(f'channels list: {channels[:15]}')
"
```

Expected:
- `rows`: hundreds (≈ 180 × ~15 = ~2700)
- `sample`: dict with keys `dia`, `channel`, `reg`, `cal` (values are strings — bq json output)
- `days`: ~180 days, last day = yesterday
- `channels`: ~10–20, contains `WEB Paid`, `Estudio Inmueble Paid`, `WEB Direct`, `Broker Direct`

If counts look wrong (e.g., 0 rows, channels missing) — STOP and check the query before continuing.

- [ ] **Step 5: Commit**

```bash
cd ~/habi/tableros-marketing
git add marketing-wbr/query_leads.sql
git commit -m "$(cat <<'EOF'
WBR: add leads + calificados query (CO)

Daily counts by (dia, channel) for last 180 days. Uses the UTM dict
fallback for "{fuente} Direct" labels. Calificados defined as
estado_id IN (20, 63) in historico_estado_v2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Spend query

**Files:**
- Create: `marketing-wbr/query_spend.sql`

- [ ] **Step 1: Write the spend query**

Create `marketing-wbr/query_spend.sql` with this exact content:

```sql
-- Marketing WBR — spend by (dia, channel) (CO)
-- Output: one row per (dia, channel) with summed spend.
-- Channel via JOIN i.campana = m.mkt_campaign_name (UTM dict).
-- Spend without channel match is dropped (reported separately).

WITH utm_dedup AS (
  SELECT *
  FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
  QUALIFY ROW_NUMBER() OVER(PARTITION BY mkt_campaign_name ORDER BY mkt_campaign_name) = 1
)

SELECT
  CAST(i.date AS STRING) AS dia,
  m.mkt_channel_medium AS channel,
  ROUND(SUM(i.spend), 0) AS spend
FROM `papyrus-data.habi_wh_bi.resumen_inversiones_mkt_co` i
LEFT JOIN utm_dedup m ON i.campana = m.mkt_campaign_name
WHERE i.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
  AND i.date < CURRENT_DATE()
  AND m.mkt_channel_medium IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2
```

- [ ] **Step 2: Run query and save to /tmp**

Run:

```bash
bq --project_id=papyrus-data query --use_legacy_sql=false --format=json --max_rows=200000 < marketing-wbr/query_spend.sql > /tmp/wbr_spend_co.json
```

Expected: exits 0, file non-empty.

- [ ] **Step 3: Validate the output and report match rate**

Run:

```bash
python3 -c "
import json
spend = json.load(open('/tmp/wbr_spend_co.json'))
print(f'rows: {len(spend)}')
print(f'sample: {spend[0]}')
total_spend = sum(float(r['spend']) for r in spend)
channels = sorted({r['channel'] for r in spend})
print(f'total_spend (180d): \${total_spend:,.0f}')
print(f'channels with spend: {channels}')
"

# Now check unmatched spend (channels NULL)
bq --project_id=papyrus-data query --use_legacy_sql=false --format=prettyjson --max_rows=10 "
WITH utm_dedup AS (
  SELECT * FROM \`sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia\`
  QUALIFY ROW_NUMBER() OVER(PARTITION BY mkt_campaign_name ORDER BY mkt_campaign_name) = 1
)
SELECT
  COUNTIF(m.mkt_channel_medium IS NULL) AS rows_unmatched,
  COUNT(*) AS rows_total,
  ROUND(100 * SUM(IF(m.mkt_channel_medium IS NULL, i.spend, 0)) / SUM(i.spend), 2) AS pct_spend_unmatched
FROM \`papyrus-data.habi_wh_bi.resumen_inversiones_mkt_co\` i
LEFT JOIN utm_dedup m ON i.campana = m.mkt_campaign_name
WHERE i.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
  AND i.date < CURRENT_DATE()
"
```

Expected:
- `rows`: hundreds (~180 days × ~5 channels with spend)
- `total_spend`: large positive number
- `channels with spend`: includes `WEB Paid`, `Estudio Inmueble Paid`, `lead_forms Paid`
- `pct_spend_unmatched` < 5% (acceptable). If higher, note it in PR description and continue — the spec accepts unattributed spend being dropped.

- [ ] **Step 4: Commit**

```bash
git add marketing-wbr/query_spend.sql
git commit -m "$(cat <<'EOF'
WBR: add spend by channel query (CO)

Joins resumen_inversiones_mkt_co to UTM dict via i.campana =
m.mkt_campaign_name. Drops spend without channel match.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: build_data.py

**Files:**
- Create: `marketing-wbr/build_data.py`

- [ ] **Step 1: Write the builder script**

Create `marketing-wbr/build_data.py` with this exact content:

```python
#!/usr/bin/env python3
"""
Combines BigQuery JSON outputs (leads + spend) into compact data.json
for the Marketing WBR dashboard.

Usage:
  build_data.py <leads_co.json> <spend_co.json> <output.json>

Output shape:
  {
    "updated": "YYYY-MM-DD",
    "co": {
      "by_day": {
        "YYYY-MM-DD": {
          "<channel>": {"reg": int, "cal": int, "spend": int|null}
        }
      }
    },
    "mx": {"by_day": {}}
  }
"""
import json
import sys
from collections import defaultdict
from datetime import date


def load_country(leads_path, spend_path):
    leads = json.load(open(leads_path))
    spend = json.load(open(spend_path))

    by_day = defaultdict(dict)

    for r in leads:
        cell = by_day[r['dia']].setdefault(r['channel'], {'reg': 0, 'cal': 0, 'spend': None})
        cell['reg'] = int(r['reg'])
        cell['cal'] = int(r['cal'])

    for s in spend:
        cell = by_day[s['dia']].setdefault(s['channel'], {'reg': 0, 'cal': 0, 'spend': None})
        cell['spend'] = int(float(s['spend']))

    return {'by_day': dict(by_day)}


def main():
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <leads_co.json> <spend_co.json> <output.json>")
        sys.exit(1)

    leads_co, spend_co, output = sys.argv[1:]

    data = {
        'updated': date.today().isoformat(),
        'co': load_country(leads_co, spend_co),
        'mx': {'by_day': {}},
    }

    with open(output, 'w') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    n_days = len(data['co']['by_day'])
    n_cells = sum(len(d) for d in data['co']['by_day'].values())
    size = len(json.dumps(data))
    print(f"OK: {output} ({size:,} bytes, {n_days} days CO, {n_cells} cells)")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run it locally**

Run:

```bash
cd ~/habi/tableros-marketing
python3 marketing-wbr/build_data.py /tmp/wbr_leads_co.json /tmp/wbr_spend_co.json marketing-wbr/data.json
```

Expected: prints `OK: marketing-wbr/data.json (XXX,XXX bytes, ~180 days CO, ~2700 cells)`. Size should be < 500 KB.

- [ ] **Step 3: Inspect the produced data.json**

Run:

```bash
python3 -c "
import json
d = json.load(open('marketing-wbr/data.json'))
print('keys:', list(d.keys()))
print('co days:', len(d['co']['by_day']))
sample_day = sorted(d['co']['by_day'].keys())[-1]
print(f'sample day {sample_day}:')
for ch, vals in d['co']['by_day'][sample_day].items():
    print(f'  {ch}: {vals}')
"
```

Expected:
- `keys: ['updated', 'co', 'mx']`
- `co days: ~180`
- Sample day shows ~10 channels with their `{reg, cal, spend}` values. Spend is `None` for organic channels (Direct, SAC, Community, Referral, etc.).

- [ ] **Step 4: Commit (script + first data.json)**

```bash
git add marketing-wbr/build_data.py marketing-wbr/data.json
git commit -m "$(cat <<'EOF'
WBR: add build_data.py and initial data.json (CO)

Merges leads and spend BQ outputs into compact by_day shape. MX block
is initialized empty until the MX queries are added.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: HTML skeleton (header + selectors + theme, no matrix yet)

**Files:**
- Create: `marketing-wbr/index.html`
- Reference: `okr-marketing/index.html` (for theme variables, theme toggle script, back-link styles)

- [ ] **Step 1: Read the reference dashboard**

Run:

```bash
head -120 ~/habi/tableros-marketing/okr-marketing/index.html
```

Look for: `<style>` block with `:root` variables, `.back-link` styles, theme toggle button + script, favicon `<link>`.

- [ ] **Step 2: Write the HTML skeleton**

Create `marketing-wbr/index.html` with this exact content:

```html
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📢</text></svg>">
<title>Marketing WBR — Habi</title>
<style>
  :root {
    --bg: #0f172a;
    --card: #1e293b;
    --card-hover: #1e2942;
    --border: #334155;
    --text-title: #f8fafc;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --text-muted-2: #64748b;
    --accent: #818cf8;
    --good-bg: rgba(22, 163, 74, 0.18);
    --good-fg: #4ade80;
    --bad-bg: rgba(220, 38, 38, 0.18);
    --bad-fg: #f87171;
  }
  body.light {
    --bg: #f5f7fa;
    --card: #ffffff;
    --card-hover: #eef2ff;
    --border: #e2e8f0;
    --text-title: #0f172a;
    --text: #334155;
    --text-muted: #64748b;
    --text-muted-2: #94a3b8;
    --accent: #6366f1;
    --good-bg: rgba(22, 163, 74, 0.13);
    --good-fg: #15803d;
    --bad-bg: rgba(220, 38, 38, 0.13);
    --bad-fg: #b91c1c;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding: 24px; transition: background 0.2s, color 0.2s; }
  .theme-btn { position: fixed; top: 20px; right: 24px; background: var(--card); border: 1px solid var(--border); color: var(--text-muted); border-radius: 6px; padding: 4px 10px; font-size: 14px; cursor: pointer; z-index: 10; }
  .theme-btn:hover { color: var(--accent); }
  .back-link { display: inline-block; margin-bottom: 16px; color: var(--text-muted); text-decoration: none; font-size: 13px; }
  .back-link:hover { color: var(--accent); }
  .header { max-width: 1400px; margin: 0 auto 24px; }
  .header h1 { font-size: 26px; font-weight: 600; color: var(--text-title); margin-bottom: 6px; }
  .header h1 span { color: var(--accent); }
  .header p { font-size: 14px; color: var(--text-muted); }

  .controls { max-width: 1400px; margin: 0 auto 20px; display: flex; gap: 24px; align-items: center; flex-wrap: wrap; }
  .control-group { display: flex; gap: 6px; align-items: center; }
  .control-group label { font-size: 13px; color: var(--text-muted); margin-right: 6px; }
  .pill { background: var(--card); border: 1px solid var(--border); color: var(--text); padding: 6px 14px; border-radius: 20px; cursor: pointer; font-size: 13px; transition: all 0.15s; }
  .pill:hover { border-color: var(--accent); }
  .pill.active { background: var(--accent); color: #0f172a; border-color: var(--accent); font-weight: 600; }
  .pill:disabled { opacity: 0.45; cursor: not-allowed; }

  .period-info { font-size: 13px; color: var(--text-muted-2); margin-left: auto; }
  .period-info strong { color: var(--text); }

  .matrix-wrap { max-width: 1400px; margin: 0 auto; background: var(--card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  .matrix-empty { padding: 48px; text-align: center; color: var(--text-muted); }

  footer { max-width: 1400px; margin: 32px auto 0; font-size: 12px; color: var(--text-muted-2); text-align: center; }
</style>
</head>
<body>
  <button type="button" class="theme-btn" id="themeToggle" onclick="toggleTheme()" aria-label="Cambiar tema">🌙</button>

  <a href="https://camilootoya-habi.github.io/tableros-marketing-habi/" class="back-link">← Volver al hub</a>

  <div class="header">
    <h1>Marketing <span>WBR</span></h1>
    <p>Matriz Dupont por canal: comparativo vs período anterior. Color verde/rojo si la variación supera ±10%.</p>
  </div>

  <div class="controls">
    <div class="control-group">
      <label>País:</label>
      <button type="button" class="pill active" data-country="co">Colombia</button>
      <button type="button" class="pill" data-country="mx" disabled title="Próximamente">México</button>
    </div>
    <div class="control-group">
      <label>Ventana:</label>
      <button type="button" class="pill active" data-window="7">7 días</button>
      <button type="button" class="pill" data-window="14">14 días</button>
      <button type="button" class="pill" data-window="28">28 días</button>
      <button type="button" class="pill" data-window="56">56 días</button>
    </div>
    <div class="period-info" id="periodInfo">cargando…</div>
  </div>

  <div class="matrix-wrap">
    <div id="matrix" class="matrix-empty">cargando datos…</div>
  </div>

  <footer>habi · marketing analytics · WBR</footer>

<script>
  // Theme toggle (same key as other dashboards)
  function toggleTheme() {
    const isLight = document.body.classList.toggle('light');
    localStorage.setItem('tablero-theme', isLight ? 'light' : 'dark');
    document.getElementById('themeToggle').textContent = isLight ? '☀️' : '🌙';
  }
  (function initTheme() {
    const saved = localStorage.getItem('tablero-theme');
    if (saved !== 'dark') document.body.classList.add('light');
    document.getElementById('themeToggle').textContent = document.body.classList.contains('light') ? '☀️' : '🌙';
  })();

  // State
  const STATE = {
    country: localStorage.getItem('wbr-country') || 'co',
    window: parseInt(localStorage.getItem('wbr-window') || '7', 10),
    data: null,
  };

  // Pill button wiring
  document.querySelectorAll('.pill[data-country]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      STATE.country = btn.dataset.country;
      localStorage.setItem('wbr-country', STATE.country);
      syncPills(); render();
    });
  });
  document.querySelectorAll('.pill[data-window]').forEach(btn => {
    btn.addEventListener('click', () => {
      STATE.window = parseInt(btn.dataset.window, 10);
      localStorage.setItem('wbr-window', String(STATE.window));
      syncPills(); render();
    });
  });

  function syncPills() {
    document.querySelectorAll('.pill[data-country]').forEach(b => {
      b.classList.toggle('active', b.dataset.country === STATE.country);
    });
    document.querySelectorAll('.pill[data-window]').forEach(b => {
      b.classList.toggle('active', parseInt(b.dataset.window, 10) === STATE.window);
    });
  }

  function render() {
    document.getElementById('matrix').textContent = `país=${STATE.country} ventana=${STATE.window}d (matriz pendiente)`;
    document.getElementById('periodInfo').textContent = '';
  }

  // Load data
  fetch('data.json')
    .then(r => r.json())
    .then(d => { STATE.data = d; syncPills(); render(); })
    .catch(err => { document.getElementById('matrix').textContent = 'Error cargando datos: ' + err; });
</script>
</body>
</html>
```

- [ ] **Step 3: Open it locally and verify the skeleton works**

Run a local server in the background:

```bash
cd ~/habi/tableros-marketing && python3 -m http.server 8765 &
sleep 1
curl -s http://localhost:8765/marketing-wbr/ | grep -E '(Marketing.*WBR|cargando)' | head -5
```

Expected: matches both `Marketing` `WBR` heading and `cargando datos…` placeholder.

Then open in a browser: `http://localhost:8765/marketing-wbr/`. Verify visually:
- Header, back-link, theme toggle visible
- Country pills: CO active, MX disabled
- Window pills: 7d active by default
- Bottom area shows `país=co ventana=7d (matriz pendiente)`
- Theme toggle works (click it, switches dark/light, persists on reload)
- Window pill click changes the placeholder text and persists in localStorage

Stop the server: `kill %1` (or note the PID and kill it later).

- [ ] **Step 4: Commit**

```bash
git add marketing-wbr/index.html
git commit -m "$(cat <<'EOF'
WBR: add HTML skeleton with selectors and theme toggle

Header, back-link, country (CO active, MX disabled), window pills
(7/14/28/56), theme toggle, data.json fetch. Matrix render is a
placeholder; comes in the next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Window aggregation logic (no rendering yet)

**Files:**
- Modify: `marketing-wbr/index.html` (replace the placeholder `render()` and add helpers)

- [ ] **Step 1: Add aggregation helpers inside the `<script>` block**

In `marketing-wbr/index.html`, find the `function render()` block and replace it (and only it) with the following helpers + a new render that logs the aggregation to console (still no DOM matrix). Insert this code right before the existing `// Load data` comment:

```javascript
  // --- Aggregation ---

  // ISO date math (no Date timezone surprises). Input/output: 'YYYY-MM-DD'.
  function addDays(iso, n) {
    const [y, m, d] = iso.split('-').map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d));
    dt.setUTCDate(dt.getUTCDate() + n);
    return dt.toISOString().slice(0, 10);
  }

  function lastUpdatedDay(byDay) {
    const days = Object.keys(byDay);
    return days.length ? days.sort().slice(-1)[0] : null;
  }

  // For window N: actual = [last - (N-1) … last], prev = [last - (2N-1) … last - N]
  function windowRanges(lastDay, n) {
    const actualEnd = lastDay;
    const actualStart = addDays(actualEnd, -(n - 1));
    const prevEnd = addDays(actualStart, -1);
    const prevStart = addDays(prevEnd, -(n - 1));
    return { actualStart, actualEnd, prevStart, prevEnd };
  }

  // Sum by channel inside [start, end] inclusive
  function aggregateRange(byDay, start, end) {
    const out = {}; // channel -> {reg, cal, spend, hadSpend}
    for (const day of Object.keys(byDay)) {
      if (day < start || day > end) continue;
      for (const [channel, v] of Object.entries(byDay[day])) {
        const cell = out[channel] || (out[channel] = { reg: 0, cal: 0, spend: 0, hadSpend: false });
        cell.reg += v.reg || 0;
        cell.cal += v.cal || 0;
        if (v.spend != null) { cell.spend += v.spend; cell.hadSpend = true; }
      }
    }
    return out;
  }

  // Build the matrix model: row per channel + TOTAL, with actual + prev numbers
  function buildModel() {
    if (!STATE.data) return null;
    const byDay = (STATE.data[STATE.country] || {}).by_day || {};
    const last = lastUpdatedDay(byDay);
    if (!last) return null;
    const r = windowRanges(last, STATE.window);

    const aActual = aggregateRange(byDay, r.actualStart, r.actualEnd);
    const aPrev   = aggregateRange(byDay, r.prevStart,   r.prevEnd);

    const allChannels = new Set([...Object.keys(aActual), ...Object.keys(aPrev)]);
    const rows = [];
    for (const ch of allChannels) {
      rows.push({
        channel: ch,
        actual: aActual[ch] || { reg: 0, cal: 0, spend: 0, hadSpend: false },
        prev:   aPrev[ch]   || { reg: 0, cal: 0, spend: 0, hadSpend: false },
      });
    }
    rows.sort((a, b) => b.actual.reg - a.actual.reg);

    // TOTAL row (sum of channels)
    const total = {
      channel: 'TOTAL',
      actual: { reg: 0, cal: 0, spend: 0, hadSpend: false },
      prev:   { reg: 0, cal: 0, spend: 0, hadSpend: false },
    };
    for (const row of rows) {
      ['reg', 'cal', 'spend'].forEach(k => {
        total.actual[k] += row.actual[k];
        total.prev[k]   += row.prev[k];
      });
      total.actual.hadSpend = total.actual.hadSpend || row.actual.hadSpend;
      total.prev.hadSpend   = total.prev.hadSpend   || row.prev.hadSpend;
    }

    return { ranges: r, lastDay: last, rows: [total, ...rows] };
  }

  function render() {
    const model = buildModel();
    if (!model) {
      document.getElementById('matrix').textContent = 'sin datos';
      return;
    }
    const r = model.ranges;
    document.getElementById('periodInfo').innerHTML =
      `Actual: <strong>${r.actualStart} → ${r.actualEnd}</strong> · ` +
      `vs Anterior: <strong>${r.prevStart} → ${r.prevEnd}</strong>`;

    // Temporary: dump model to the matrix area for visual inspection
    document.getElementById('matrix').textContent =
      JSON.stringify(model.rows.slice(0, 5), null, 2);
    console.log('WBR model:', model);
  }
```

- [ ] **Step 2: Reload locally and verify**

```bash
cd ~/habi/tableros-marketing && python3 -m http.server 8765 &
sleep 1
```

Open `http://localhost:8765/marketing-wbr/` in the browser. Verify:
- "Período actual:" line shows two date ranges, with actual ending yesterday and prev being the 7 days right before it.
- The matrix area shows JSON of the first 5 rows (TOTAL + top 4 channels by registros).
- Open browser DevTools console: `WBR model:` log shows the full model (rows array including TOTAL).
- Click 28-day pill: ranges and numbers update; rows reorder.
- Click reload: window selection persists.

Kill the server: `kill %1`.

- [ ] **Step 3: Commit**

```bash
git add marketing-wbr/index.html
git commit -m "$(cat <<'EOF'
WBR: aggregate data by window and channel

Adds date math, aggregateRange, and buildModel. Window N uses last
day in data as anchor; prev window is the N days immediately before.
TOTAL row is the sum of channels. Matrix DOM render comes next; for
now the model is dumped to the page and console for verification.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Render the matrix with coloring + tooltips

**Files:**
- Modify: `marketing-wbr/index.html` (replace the temporary `render()` body and add table CSS + helpers)

- [ ] **Step 1: Add table CSS inside the `<style>` block**

In `marketing-wbr/index.html`, inside the existing `<style>` block, add these rules just before the closing `</style>`:

```css
  table.matrix { width: 100%; border-collapse: collapse; font-size: 13px; }
  table.matrix th, table.matrix td { padding: 10px 14px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }
  table.matrix th { background: var(--bg); color: var(--text-muted); font-weight: 500; cursor: pointer; user-select: none; position: sticky; top: 0; z-index: 2; }
  table.matrix th.col-channel, table.matrix td.col-channel { text-align: left; color: var(--text); }
  table.matrix tbody tr.total { background: var(--bg); position: sticky; top: 41px; z-index: 1; }
  table.matrix tbody tr.total td { font-weight: 700; color: var(--text-title); border-bottom: 2px solid var(--border); }
  table.matrix td .val { display: block; color: var(--text-title); font-weight: 500; }
  table.matrix td .delta { display: block; font-size: 11px; color: var(--text-muted); margin-top: 2px; }
  table.matrix td.cell-good { background: var(--good-bg); }
  table.matrix td.cell-good .delta { color: var(--good-fg); font-weight: 600; }
  table.matrix td.cell-bad { background: var(--bad-bg); }
  table.matrix td.cell-bad .delta { color: var(--bad-fg); font-weight: 600; }
  table.matrix td.dim { color: var(--text-muted-2); }
```

- [ ] **Step 2: Replace the temporary `render()` with the real one**

In the `<script>` block, replace the entire current `function render()` body with this version, and add the helper functions just above it:

```javascript
  // --- Formatters ---
  const FMT_INT = new Intl.NumberFormat('en-US');
  function fmtMoney(n) {
    if (n == null) return '—';
    if (n >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'k';
    return '$' + FMT_INT.format(Math.round(n));
  }
  function fmtCpl(n) {
    if (n == null) return '—';
    if (n >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'k';
    return '$' + FMT_INT.format(Math.round(n));
  }
  function fmtInt(n) {
    if (n == null) return '—';
    return FMT_INT.format(Math.round(n));
  }
  function fmtPct(n) {
    if (n == null) return '—';
    return (n * 100).toFixed(1) + '%';
  }
  function fmtDelta(d) {
    if (d == null) return '';
    if (d === Infinity) return 'Δ nuevo';
    const sign = d > 0 ? '+' : '';
    return 'Δ ' + sign + (d * 100).toFixed(1) + '%';
  }

  // --- Indicator definitions ---
  // direction: 'up' = higher is better, 'down' = lower is better, 'none' = no coloring.
  // value(actual): returns the displayable number for this indicator.
  // deltaValue(a, p): returns the relative delta a vs p (or null/Infinity for edge cases).
  const INDICATORS = [
    {
      key: 'spend', label: 'Inversión', direction: 'none',
      value: r => r.hadSpend ? r.spend : null,
      fmt: v => fmtMoney(v),
    },
    {
      key: 'cpl', label: 'CPL', direction: 'down',
      value: r => (r.hadSpend && r.reg > 0) ? r.spend / r.reg : null,
      fmt: v => fmtCpl(v),
    },
    {
      key: 'reg', label: 'Registros', direction: 'up',
      value: r => r.reg,
      fmt: v => fmtInt(v),
    },
    {
      key: 'cvr', label: 'CVR R→C', direction: 'up',
      value: r => r.reg > 0 ? r.cal / r.reg : null,
      fmt: v => fmtPct(v),
    },
    {
      key: 'cal', label: 'Calificados', direction: 'up',
      value: r => r.cal,
      fmt: v => fmtInt(v),
    },
  ];

  function deltaPct(actual, prev) {
    if (actual == null || prev == null) return null;
    if (prev === 0 && actual === 0) return null;
    if (prev === 0) return Infinity; // new vs nothing
    return (actual - prev) / prev;
  }

  function colorClass(delta, direction) {
    if (direction === 'none' || delta == null) return '';
    if (delta === Infinity) return 'cell-good';
    const t = 0.10;
    if (direction === 'up') {
      if (delta > t)  return 'cell-good';
      if (delta < -t) return 'cell-bad';
    } else { // down
      if (delta < -t) return 'cell-good';
      if (delta > t)  return 'cell-bad';
    }
    return '';
  }

  function render() {
    const model = buildModel();
    const wrap = document.getElementById('matrix');
    if (!model) { wrap.className = 'matrix-empty'; wrap.textContent = 'sin datos'; return; }
    wrap.className = '';

    const r = model.ranges;
    document.getElementById('periodInfo').innerHTML =
      `Actual: <strong>${r.actualStart} → ${r.actualEnd}</strong> · ` +
      `vs Anterior: <strong>${r.prevStart} → ${r.prevEnd}</strong>`;

    let html = '<table class="matrix"><thead><tr><th class="col-channel">Canal</th>';
    for (const ind of INDICATORS) html += `<th>${ind.label}</th>`;
    html += '</tr></thead><tbody>';

    for (const row of model.rows) {
      const isTotal = row.channel === 'TOTAL';
      html += `<tr class="${isTotal ? 'total' : ''}"><td class="col-channel">${escapeHtml(row.channel)}</td>`;
      for (const ind of INDICATORS) {
        const actualVal = ind.value(row.actual);
        const prevVal   = ind.value(row.prev);
        const delta     = deltaPct(actualVal, prevVal);
        const color     = colorClass(delta, ind.direction);
        const valStr    = ind.fmt(actualVal);
        const dim       = (actualVal == null) ? 'dim' : '';
        const tip       = `Actual: ${ind.fmt(actualVal)} · Anterior: ${ind.fmt(prevVal)}` +
                          (delta != null && delta !== Infinity ? ` · Δ ${(delta * 100).toFixed(1)}%` : '');
        html += `<td class="${color} ${dim}" title="${escapeHtml(tip)}">` +
                `<span class="val">${valStr}</span>` +
                `<span class="delta">${fmtDelta(delta)}</span></td>`;
      }
      html += '</tr>';
    }
    html += '</tbody></table>';
    wrap.innerHTML = html;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
```

- [ ] **Step 3: Reload and verify visually**

```bash
cd ~/habi/tableros-marketing && python3 -m http.server 8765 &
sleep 1
```

Open `http://localhost:8765/marketing-wbr/`. Verify:
- A table renders with header `Canal | Inversión | CPL | Registros | CVR R→C | Calificados`.
- Top row is `TOTAL` (bold, sticky).
- Below it: channels sorted descending by Registros (WEB Paid likely first).
- Each numeric cell shows value on top + `Δ ±X%` below.
- Cells colored green/red where the delta exceeds ±10% (CPL inverted: lower is good = green).
- Inversión column is never colored, only delta shown.
- Channels without spend (Direct, SAC, Community) show `—` in Inversión and CPL.
- Hover on any cell: tooltip shows actual/anterior/delta.
- Switch window to 28d, 56d: table recomputes; deltas/colors update.
- Switch theme: colors stay readable in both modes.

Kill server: `kill %1`.

- [ ] **Step 4: Commit**

```bash
git add marketing-wbr/index.html
git commit -m "$(cat <<'EOF'
WBR: render Dupont matrix with coloring and tooltips

Five indicators: Inversión (no color), CPL (lower is better), Registros,
CVR R→C, Calificados. ±10% relative threshold colors cells green/red.
TOTAL row sticky on top. Tooltips show actual/anterior/delta. Channels
without spend show em-dash in Inversión/CPL.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Sortable columns

**Files:**
- Modify: `marketing-wbr/index.html` (add sort state + click handlers)

- [ ] **Step 1: Add sort state and click wiring**

In `marketing-wbr/index.html`, extend `STATE` with sort fields. Find this line:

```javascript
  const STATE = {
    country: localStorage.getItem('wbr-country') || 'co',
    window: parseInt(localStorage.getItem('wbr-window') || '7', 10),
    data: null,
  };
```

Replace it with:

```javascript
  const STATE = {
    country: localStorage.getItem('wbr-country') || 'co',
    window: parseInt(localStorage.getItem('wbr-window') || '7', 10),
    sortKey: 'reg',     // default: Registros desc
    sortDir: 'desc',
    data: null,
  };
```

- [ ] **Step 2: Update `buildModel()` to sort by `STATE.sortKey/sortDir`**

In `buildModel()`, find this line:

```javascript
    rows.sort((a, b) => b.actual.reg - a.actual.reg);
```

Replace with:

```javascript
    const ind = INDICATORS.find(i => i.key === STATE.sortKey) || INDICATORS.find(i => i.key === 'reg');
    rows.sort((a, b) => {
      const va = ind.value(a.actual);
      const vb = ind.value(b.actual);
      // Nulls always at the bottom regardless of sort direction
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return STATE.sortDir === 'asc' ? va - vb : vb - va;
    });
```

- [ ] **Step 3: Add click handlers in `render()`**

In `render()`, find this line:

```javascript
    let html = '<table class="matrix"><thead><tr><th class="col-channel">Canal</th>';
    for (const ind of INDICATORS) html += `<th>${ind.label}</th>`;
```

Replace with:

```javascript
    let html = '<table class="matrix"><thead><tr><th class="col-channel">Canal</th>';
    for (const ind of INDICATORS) {
      const arrow = STATE.sortKey === ind.key ? (STATE.sortDir === 'asc' ? ' ↑' : ' ↓') : '';
      html += `<th data-sortkey="${ind.key}">${ind.label}${arrow}</th>`;
    }
```

Then, at the very end of `render()` (after `wrap.innerHTML = html;`), add:

```javascript
    wrap.querySelectorAll('th[data-sortkey]').forEach(th => {
      th.addEventListener('click', () => {
        const k = th.dataset.sortkey;
        if (STATE.sortKey === k) {
          STATE.sortDir = STATE.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          STATE.sortKey = k;
          STATE.sortDir = 'desc';
        }
        render();
      });
    });
```

- [ ] **Step 4: Verify**

```bash
cd ~/habi/tableros-marketing && python3 -m http.server 8765 &
sleep 1
```

Open the dashboard. Verify:
- Default: Registros header shows `↓` arrow (desc).
- Click `Calificados`: rows reorder, header arrow moves there.
- Click `Calificados` again: arrow flips to `↑`, rows reverse.
- TOTAL stays first regardless (it's prepended in the array, not re-sorted) — confirm this still holds.
- Click `Inversión`: organic channels (without spend) drop to the bottom (nulls last).

Kill server: `kill %1`.

**Note on TOTAL position:** because `buildModel()` puts TOTAL at the front of the rows array *after* sorting the channel rows, sorting always leaves TOTAL on top. If during testing TOTAL moves to the middle, recheck the order: sort first, then `[total, ...rows]` after.

- [ ] **Step 5: Commit**

```bash
git add marketing-wbr/index.html
git commit -m "$(cat <<'EOF'
WBR: sortable columns with arrow indicator

Click a column header to sort by that indicator; click again to flip
direction. Default is Registros desc. TOTAL row stays sticky on top
regardless of sort.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Hub card

**Files:**
- Modify: `index.html` (root) — add a new `<a class="card">` inside the Dashboards column

- [ ] **Step 1: Add the card to the hub**

Open `~/habi/tableros-marketing/index.html`. Find this block (near the top of the Dashboards card stack — currently the Funnel Sellers card):

```html
        <a class="card" href="https://camilootoya-habi.github.io/tableros-marketing-habi/tablero-marketing/">
          <h2><span class="country">CO &amp; MX</span>Funnel Sellers</h2>
          <p>Calificación de leads para Market Maker vs Inmobiliaria por fuente, país y período.</p>
        </a>
```

Insert the WBR card immediately *before* the Funnel Sellers card (so it appears at the top of the dashboards column):

```html
        <a class="card" href="https://camilootoya-habi.github.io/tableros-marketing-habi/marketing-wbr/">
          <h2><span class="country">CO &amp; MX</span>Marketing WBR</h2>
          <p>Weekly Business Review: matriz Dupont por canal con comparativos vs período anterior. CO disponible, MX próximamente.</p>
        </a>

```

- [ ] **Step 2: Verify locally**

```bash
cd ~/habi/tableros-marketing && python3 -m http.server 8765 &
sleep 1
curl -s http://localhost:8765/ | grep -A2 'Marketing WBR'
```

Expected: shows the new card. Open `http://localhost:8765/` in a browser — the WBR card should appear at the top of the Dashboards column. Click it; should land on the WBR dashboard.

Kill server: `kill %1`.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "$(cat <<'EOF'
Hub: add Marketing WBR card

Links to the new WBR dashboard. Placed at the top of the Dashboards
column (before Funnel Sellers) since WBR is the highest-level view.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Auto-update workflow

**Files:**
- Modify: `.github/workflows/update-data.yml` — add 3 steps (leads query, spend query, build) and add `marketing-wbr/data.json` to commit step

- [ ] **Step 1: Add the WBR steps to the workflow**

Open `.github/workflows/update-data.yml`. Find the most recent step group (the `incompletos-direccion` block added previously). Insert these 3 new steps immediately after it, *before* the `Commit and push` step:

```yaml
      - name: Query Marketing WBR — leads + calificados (CO)
        if: always()
        run: |
          bq query --use_legacy_sql=false --format=json --max_rows=200000 < marketing-wbr/query_leads.sql > /tmp/wbr_leads_co.json
          echo "WBR leads CO rows: $(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1])))) ' /tmp/wbr_leads_co.json)"

      - name: Query Marketing WBR — spend (CO)
        if: always()
        run: |
          bq query --use_legacy_sql=false --format=json --max_rows=200000 < marketing-wbr/query_spend.sql > /tmp/wbr_spend_co.json
          echo "WBR spend CO rows: $(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1])))) ' /tmp/wbr_spend_co.json)"

      - name: Build Marketing WBR data.json
        if: always()
        run: |
          python3 marketing-wbr/build_data.py /tmp/wbr_leads_co.json /tmp/wbr_spend_co.json marketing-wbr/data.json
```

- [ ] **Step 2: Add `marketing-wbr/data.json` to the commit step**

In the same file, find the `Commit and push` step's `git add` line (it currently lists all the data.json files including `incompletos-direccion/data.json`). Append ` marketing-wbr/data.json` to the end of that line. The line should look like:

```yaml
          git add incompletos-colombia/data.json tablero-marketing/data.json tablero-marketing/antifunnel.json tablero-marketing/mm_sin_inmo_states.json okr-marketing/data.json pmax-mexico-quality/data.json pmax-mexico-quality/states.json creativo-pamela/data.json incompletos-direccion/data.json marketing-wbr/data.json
```

- [ ] **Step 3: Validate the YAML syntax locally**

Run:

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/update-data.yml')); print('YAML OK')"
```

Expected: prints `YAML OK`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/update-data.yml
git commit -m "$(cat <<'EOF'
WBR: hook into consolidated auto-update workflow

Adds three steps (leads query, spend query, build_data.py) and
includes marketing-wbr/data.json in the commit step. Each query step
uses if: always() so an upstream failure doesn't skip WBR.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Push and verify deploy

**Files:** none (push + verify only)

- [ ] **Step 1: Pull rebase to pick up any cron commits**

```bash
cd ~/habi/tableros-marketing && git pull --rebase origin main
```

Expected: clean fast-forward or rebase of your local commits on top of any remote auto-update commit.

- [ ] **Step 2: Push**

```bash
git push origin main
```

Expected: new commits visible on origin/main.

- [ ] **Step 3: Wait for GitHub Pages to redeploy and verify**

GitHub Pages typically rebuilds in 1–2 minutes after a push. After waiting:

```bash
# Check the dashboard is live
curl -sI https://camilootoya-habi.github.io/tableros-marketing-habi/marketing-wbr/ | head -3
```

Expected: HTTP/2 200.

```bash
# Check data.json is reachable
curl -s https://camilootoya-habi.github.io/tableros-marketing-habi/marketing-wbr/data.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('updated:', d['updated'])
print('co days:', len(d['co']['by_day']))
"
```

Expected: prints today's date (or yesterday if the cron hasn't run yet) and ~180 days. If still showing yesterday's `updated`, that's fine — the cron will refresh it tomorrow at 13:00 UTC.

- [ ] **Step 4: Open in browser and smoke-test the live site**

Visit https://camilootoya-habi.github.io/tableros-marketing-habi/marketing-wbr/ in a browser. Verify:
- Page loads, matrix renders with CO data.
- Default view: 7 days, sorted by Registros desc.
- Switching window pills (14/28/56) recomputes the matrix.
- Period info line shows the correct date ranges.
- Sorting by clicking a header works.
- Coloring is visible on cells with > ±10% delta.
- Tooltip on hover shows actual/anterior/delta.
- Theme toggle works and persists across reloads.
- Hub card on https://camilootoya-habi.github.io/tableros-marketing-habi/ links to it correctly.

- [ ] **Step 5: Manually trigger the workflow to confirm the cron path works**

In the GitHub UI: Actions → "Update data" workflow → "Run workflow" → main → green button. Wait for it to complete (~2–3 min). Verify it succeeds and produces a new commit `Auto-update data.json YYYY-MM-DD` that touches `marketing-wbr/data.json`.

If a step fails, check logs. Most common issues:
- Auth: `GCP_CREDENTIALS` secret may not have access to one of the new tables. Confirm by trying the query manually with the same creds.
- Path: ensure step `working-directory` is consistent with the rest of the workflow (default is repo root).

- [ ] **Step 6: No commit needed for this task**

If the manual run produced any data.json changes, the bot already committed them. If not, this task is just verification.

---

## Notes for the executor

- **No tests:** this codebase doesn't have an automated test suite. Verification at each step is by command output and visual inspection in the browser. Don't add a test framework unless explicitly asked.
- **DRY:** if you find yourself copy-pasting more than ~10 lines (e.g., for MX), stop and refactor — but for this CO-only first entrega, MX is intentionally a stub.
- **YAGNI:** don't add features not in the spec. No drill-down, no export-to-CSV, no MX query, no asignados, no meta — those are explicitly out of scope.
- **Frequent commits:** every task ends with one commit. Don't bundle.
- **If a step fails:** stop, diagnose, and update the plan if a step's assumption was wrong. Don't skip steps to "make it work."
- **Cron data refresh:** the workflow runs daily at 13:00 UTC. If you push outside the cron window and want fresh data immediately, trigger the workflow manually as in Task 10 step 5.
