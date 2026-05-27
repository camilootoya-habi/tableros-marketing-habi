# Hub multi-líder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir el hub de tableros en un sistema multi-líder donde el `index.html` se genera desde `meta.json` por carpeta, los queries nuevos se enchufan al cron por auto-discovery, y la gobernanza es por PR (Camilo conserva push directo).

**Architecture:** Monorepo. Cada tablero es una carpeta con un contrato (`meta.json` obligatorio, `query.sql`/`data.json` opcionales). `scripts/build_hub.py` regenera `index.html` agrupando por dueño (raíz=general, `canales/<lider>/`=líder) y por `section`. `scripts/run_queries.py` descubre y corre los `query.sql` nuevos en el cron, aditivo a los pasos a-medida existentes. El `index.html` es un artefacto generado.

**Tech Stack:** Python 3 (stdlib + pytest), `bq` CLI (BigQuery), GitHub Actions, GitHub Pages, CODEOWNERS + branch protection.

**Spec:** `docs/superpowers/specs/2026-05-26-hub-multilider-design.md`

---

## File Structure

- `scripts/build_hub.py` — genera `index.html` desde meta.json + hub.config.json + _leader.json
- `scripts/run_queries.py` — auto-discovery: corre los `query.sql` nuevos en el cron
- `scripts/templates/hub.html` — plantilla del hub (head + CSS + placeholders)
- `scripts/templates/dashboard.html` — plantilla de tablero nuevo para líderes
- `scripts/tests/test_build_hub.py` — tests del generador
- `scripts/tests/test_run_queries.py` — tests del descubridor de queries
- `scripts/tests/fixtures/` — repos de prueba en miniatura
- `hub.config.json` — header + cards externas (los 2 informes satélite)
- `<slug>/meta.json` — backfill para los 15 tableros existentes (sin `query`)
- `canales/sebastian-ciendua/_leader.json` — registro del piloto
- `.github/CODEOWNERS` — protege archivos compartidos
- `.github/workflows/update-data.yml` — modificar: agregar pasos de queries + build hub
- `CONTRIBUTING.md` — flujo para líderes

---

## Phase 1 — Convención + generador del hub

### Task 1: Scaffolding de tests + descubrimiento de tableros

**Files:**
- Create: `scripts/build_hub.py`
- Test: `scripts/tests/test_build_hub.py`
- Create: `scripts/tests/fixtures/mini_repo/incompletos-colombia/meta.json`
- Create: `scripts/tests/fixtures/mini_repo/canales/sebastian-ciendua/_leader.json`
- Create: `scripts/tests/fixtures/mini_repo/canales/sebastian-ciendua/cpa-diario/meta.json`

- [ ] **Step 1: Crear los fixtures**

`scripts/tests/fixtures/mini_repo/incompletos-colombia/meta.json`:
```json
{ "title": "Leads Incompletos", "description": "Leads en estado incompleto.", "country": "CO", "section": "dashboard", "order": 10 }
```

`scripts/tests/fixtures/mini_repo/canales/sebastian-ciendua/_leader.json`:
```json
{ "name": "Sebastián Ciendua", "channel": "Performance Colombia", "order": 1 }
```

`scripts/tests/fixtures/mini_repo/canales/sebastian-ciendua/cpa-diario/meta.json`:
```json
{ "title": "CPA diario", "description": "Costo por adquisición diario.", "country": "CO", "section": "dashboard", "order": 1, "query": "query.sql" }
```

- [ ] **Step 2: Escribir el test que falla**

```python
# scripts/tests/test_build_hub.py
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_hub

REPO = Path(__file__).parent / "fixtures" / "mini_repo"

def test_discover_dashboards_infers_owner_and_loads_meta():
    dashboards = build_hub.discover_dashboards(REPO)
    by_slug = {d["slug"]: d for d in dashboards}

    assert by_slug["incompletos-colombia"]["owner"] == "general"
    assert by_slug["incompletos-colombia"]["title"] == "Leads Incompletos"
    assert by_slug["incompletos-colombia"]["link"] == "incompletos-colombia/"

    cpa = by_slug["cpa-diario"]
    assert cpa["owner"] == "sebastian-ciendua"
    assert cpa["link"] == "canales/sebastian-ciendua/cpa-diario/"
    assert cpa["query"] == "query.sql"
```

- [ ] **Step 3: Correr el test, verificar que falla**

Run: `cd ~/habi/tableros-marketing && python3 -m pytest scripts/tests/test_build_hub.py::test_discover_dashboards_infers_owner_and_loads_meta -v`
Expected: FAIL (`AttributeError: module 'build_hub' has no attribute 'discover_dashboards'`)

- [ ] **Step 4: Implementar `discover_dashboards`**

```python
# scripts/build_hub.py
import json
from pathlib import Path

IGNORE_DIRS = {".git", ".github", "scripts", "docs", "node_modules"}

def discover_dashboards(repo_root: Path):
    """Cada carpeta con meta.json es un tablero. Dueño inferido por ubicación:
    hijo directo de la raíz = 'general'; bajo canales/<lider>/ = ese líder."""
    repo_root = Path(repo_root)
    dashboards = []
    for meta_path in sorted(repo_root.rglob("meta.json")):
        rel = meta_path.parent.relative_to(repo_root)
        parts = rel.parts
        if parts and parts[0] in IGNORE_DIRS:
            continue
        if parts[0] == "canales":
            owner = parts[1]            # canales/<lider>/<slug>
            slug = parts[-1]
            link = "/".join(parts) + "/"
        else:
            owner = "general"           # <slug> en la raíz
            slug = parts[-1]
            link = "/".join(parts) + "/"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        dashboards.append({
            "slug": slug, "owner": owner, "link": link,
            "title": meta["title"], "description": meta["description"],
            "country": meta["country"], "section": meta.get("section", "dashboard"),
            "order": meta.get("order", 9999), "query": meta.get("query"),
        })
    return dashboards
```

- [ ] **Step 5: Correr el test, verificar que pasa**

Run: `cd ~/habi/tableros-marketing && python3 -m pytest scripts/tests/test_build_hub.py -v`
Expected: PASS (si `pytest` no está: `pip install pytest`)

- [ ] **Step 6: Commit**

```bash
git add scripts/build_hub.py scripts/tests/
git commit -m "feat(hub): discover_dashboards con inferencia de dueño"
```

---

### Task 2: Renderizar una card

**Files:**
- Modify: `scripts/build_hub.py`
- Test: `scripts/tests/test_build_hub.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_render_card_internal_and_country_chip():
    card = build_hub.render_card({
        "title": "CPA diario", "description": "Costo por adquisición.",
        "country": "CO", "link": "canales/sebastian-ciendua/cpa-diario/",
    })
    assert 'href="canales/sebastian-ciendua/cpa-diario/"' in card
    assert "CPA diario" in card
    assert '<span class="country">CO</span>' in card
    assert "Costo por adquisición." in card

def test_render_card_escapes_html():
    card = build_hub.render_card({
        "title": "A & B", "description": "x < y", "country": "CO", "link": "a/",
    })
    assert "A &amp; B" in card
    assert "x &lt; y" in card
```

- [ ] **Step 2: Correr, verificar falla**

Run: `python3 -m pytest scripts/tests/test_build_hub.py::test_render_card_internal_and_country_chip -v`
Expected: FAIL (`has no attribute 'render_card'`)

- [ ] **Step 3: Implementar `render_card`**

```python
from html import escape

def render_card(d: dict) -> str:
    country = d.get("country", "")
    chips = "".join(
        f'<span class="country">{escape(c.strip())}</span>'
        for c in country.split("&")
    ) if country else ""
    return (
        f'        <a class="card" href="{escape(d["link"])}">\n'
        f'          <h2>{chips}{escape(d["title"])}</h2>\n'
        f'          <p>{escape(d["description"])}</p>\n'
        f'        </a>'
    )
```

- [ ] **Step 4: Correr, verificar pasa**

Run: `python3 -m pytest scripts/tests/test_build_hub.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/build_hub.py scripts/tests/test_build_hub.py
git commit -m "feat(hub): render_card con chips de país y escape HTML"
```

---

### Task 3: Agrupar y ordenar por dueño → sección

**Files:**
- Modify: `scripts/build_hub.py`
- Test: `scripts/tests/test_build_hub.py`

- [ ] **Step 1: Escribir el test que falla**

```python
SECTION_LABELS = {"analysis": "Analysis", "dashboard": "Dashboards", "reference": "Reference"}

def test_render_owner_block_groups_by_section_in_order():
    cards = [
        {"title": "B dash", "description": "", "country": "CO", "link": "b/", "section": "dashboard", "order": 2},
        {"title": "A dash", "description": "", "country": "CO", "link": "a/", "section": "dashboard", "order": 1},
        {"title": "An analysis", "description": "", "country": "CO", "link": "an/", "section": "analysis", "order": 1},
    ]
    html = build_hub.render_owner_block("General · Marketing", cards)
    # El título de sección sale
    assert "General · Marketing" in html
    # Analysis aparece antes que Dashboards
    assert html.index(">Analysis<") < html.index(">Dashboards<")
    # Dentro de Dashboards, A (order 1) antes que B (order 2)
    assert html.index("A dash") < html.index("B dash")
```

- [ ] **Step 2: Correr, verificar falla**

Run: `python3 -m pytest scripts/tests/test_build_hub.py::test_render_owner_block_groups_by_section_in_order -v`
Expected: FAIL (`has no attribute 'render_owner_block'`)

- [ ] **Step 3: Implementar `render_owner_block`**

```python
SECTION_ORDER = ["analysis", "dashboard", "reference"]
SECTION_LABELS = {"analysis": "Analysis", "dashboard": "Dashboards", "reference": "Reference"}

def render_owner_block(heading: str, cards: list) -> str:
    columns = []
    for section in SECTION_ORDER:
        in_section = sorted(
            [c for c in cards if c.get("section", "dashboard") == section],
            key=lambda c: (c.get("order", 9999), c["title"].lower()),
        )
        if not in_section:
            continue
        cards_html = "\n\n".join(render_card(c) for c in in_section)
        columns.append(
            f'    <div class="column">\n'
            f'      <h2 class="section-title"><span>{escape(SECTION_LABELS[section])}</span></h2>\n'
            f'      <div class="card-stack">\n{cards_html}\n      </div>\n'
            f'    </div>'
        )
    columns_html = "\n".join(columns)
    return (
        f'  <h2 class="owner-title">{escape(heading)}</h2>\n'
        f'  <div class="columns">\n{columns_html}\n  </div>'
    )
```

- [ ] **Step 4: Correr, verificar pasa**

Run: `python3 -m pytest scripts/tests/test_build_hub.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/build_hub.py scripts/tests/test_build_hub.py
git commit -m "feat(hub): render_owner_block agrupa por sección y ordena"
```

---

### Task 4: Plantilla + ensamblaje completo de la página

**Files:**
- Create: `scripts/templates/hub.html`
- Modify: `scripts/build_hub.py`
- Test: `scripts/tests/test_build_hub.py`

- [ ] **Step 1: Crear la plantilla `scripts/templates/hub.html`**

Copiar verbatim el `<head>` completo (incluye favicon 📢 y todo el `<style>`, hoy en `index.html:6-56`) y el `<script>` de `toggleTheme` (`index.html:57-63`) y el de init de tema (`index.html:175-182`). Reemplazar solo el contenido del `<body>` por placeholders. Agregar al `<style>` la regla nueva de título de dueño:
```css
.owner-title { font-size: 26px; font-weight: 700; color: var(--text-title); margin: 8px 4px 20px; padding-top: 24px; border-top: 1px solid var(--border); width: 100%; max-width: 1400px; }
.owner-title:first-of-type { border-top: none; padding-top: 0; }
```
Estructura del body en la plantilla:
```html
<body>
  <button type="button" class="theme-btn" id="themeToggle" onclick="toggleTheme()" aria-label="Cambiar tema">🌙</button>
  <div class="header">
    <h1>{{TITLE}}</h1>
    <p>{{SUBTITLE}}</p>
  </div>
{{CONTENT}}
  <footer>habi · marketing analytics</footer>
  <!-- (mismo script de init de tema que el index.html actual) -->
</body>
```
Comentario obligatorio arriba del `<!DOCTYPE html>`: `<!-- GENERADO por scripts/build_hub.py — NO editar a mano -->`

- [ ] **Step 2: Escribir el test que falla**

```python
def test_build_page_orders_general_then_leaders():
    dashboards = build_hub.discover_dashboards(REPO)
    leaders = build_hub.discover_leaders(REPO)
    config = {"title": "Growth & Marketing", "subtitle": "sub", "general": {"title": "General · Marketing", "order": 0}, "external_cards": []}
    html = build_hub.build_page(dashboards, leaders, config, template=build_hub.load_template())
    assert "NO editar a mano" in html
    assert "Growth &amp; Marketing" in html or "Growth & Marketing" in html
    # General antes que el líder
    assert html.index("General · Marketing") < html.index("Sebastián Ciendua · Performance Colombia")
    # El tablero del líder está enlazado
    assert "canales/sebastian-ciendua/cpa-diario/" in html

def test_discover_leaders_reads_leader_json():
    leaders = build_hub.discover_leaders(REPO)
    assert leaders["sebastian-ciendua"]["name"] == "Sebastián Ciendua"
    assert leaders["sebastian-ciendua"]["channel"] == "Performance Colombia"
```

- [ ] **Step 3: Correr, verificar falla**

Run: `python3 -m pytest scripts/tests/test_build_hub.py::test_build_page_orders_general_then_leaders -v`
Expected: FAIL (`has no attribute 'discover_leaders'`)

- [ ] **Step 4: Implementar `discover_leaders`, `load_template`, `build_page`, `main`**

```python
TEMPLATE_PATH = Path(__file__).parent / "templates" / "hub.html"

def discover_leaders(repo_root: Path) -> dict:
    repo_root = Path(repo_root)
    leaders = {}
    for lj in sorted((repo_root / "canales").glob("*/_leader.json")) if (repo_root / "canales").exists() else []:
        data = json.loads(lj.read_text(encoding="utf-8"))
        leaders[lj.parent.name] = data
    return leaders

def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")

def build_page(dashboards, leaders, config, template) -> str:
    blocks = []
    # General primero
    general_cards = [d for d in dashboards if d["owner"] == "general"] + [
        {**c, "link": c["url"]} for c in config.get("external_cards", [])
    ]
    blocks.append(render_owner_block(config["general"]["title"], general_cards))
    # Luego cada líder por orden
    for lid in sorted(leaders, key=lambda k: leaders[k].get("order", 9999)):
        ld = leaders[lid]
        heading = f'{ld["name"]} · {ld["channel"]}'
        lcards = [d for d in dashboards if d["owner"] == lid]
        if lcards:
            blocks.append(render_owner_block(heading, lcards))
    content = "\n".join(blocks)
    return (template
            .replace("{{TITLE}}", escape(config["title"]))
            .replace("{{SUBTITLE}}", escape(config["subtitle"]))
            .replace("{{CONTENT}}", content))

def main():
    repo = Path(__file__).resolve().parents[1]
    config = json.loads((repo / "hub.config.json").read_text(encoding="utf-8"))
    html = build_page(discover_dashboards(repo), discover_leaders(repo), config, load_template())
    (repo / "index.html").write_text(html, encoding="utf-8")
    print(f"index.html regenerado ({len(html)} bytes)")

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Correr, verificar pasa**

Run: `python3 -m pytest scripts/tests/test_build_hub.py -v`
Expected: PASS (todos)

- [ ] **Step 6: Commit**

```bash
git add scripts/build_hub.py scripts/templates/hub.html scripts/tests/test_build_hub.py
git commit -m "feat(hub): plantilla + build_page (general arriba, líderes inline) + CLI"
```

---

### Task 5: `hub.config.json` con header y cards externas

**Files:**
- Create: `hub.config.json`

- [ ] **Step 1: Crear `hub.config.json`**

```json
{
  "title": "Growth & Marketing",
  "subtitle": "Lo que no se mide no se mejora — y acá buscamos mejora continua.",
  "general": { "title": "General · Marketing", "order": 0 },
  "external_cards": [
    { "section": "analysis", "order": 1, "title": "Análisis de asignados — 2026",
      "description": "Postmortem de la caída de asignados desde el 12 de marzo: nuevo Backbone, recalibración de metas y plan para recuperar volumen.",
      "country": "CO", "url": "https://camilootoya-habi.github.io/analisis-asignados-co/" },
    { "section": "analysis", "order": 2, "title": "Postmortem campaña Multimedios — MTY",
      "description": "Impacto de la campaña ALL-IN TUHABI en Monterrey, marzo 2026: tráfico, registros, conversión y funnel comercial.",
      "country": "MX", "url": "https://camilootoya-habi.github.io/analisis-mty-multimedios/" }
  ]
}
```

- [ ] **Step 2: Validar que parsea**

Run: `python3 -c "import json; json.load(open('hub.config.json')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add hub.config.json
git commit -m "feat(hub): hub.config.json con header y cards externas (informes satélite)"
```

---

### Task 6: Backfill de `meta.json` para los 15 tableros existentes

**Files:**
- Create: `<slug>/meta.json` para cada uno de los 15 (sin campo `query`).

Mapa de slugs → `(section, country)` extraído del `index.html` actual:

| slug | section | country |
|------|---------|---------|
| incompletos-colombia | dashboard | CO |
| incompletos-direccion | dashboard | CO & MX |
| marketing-wbr | dashboard | CO & MX |
| wbr-2-0 | dashboard | CO & MX |
| asignados-creacion | dashboard | CO & MX |
| prioridad-mm | dashboard | CO & MX |
| tablero-marketing | dashboard | CO & MX |
| okr-marketing | dashboard | CO & MX |
| pmax-mexico-quality | dashboard | MX |
| creativo-pamela | dashboard | MX |
| funnel-fuentes | dashboard | CO |
| calificados-mm-inmo | dashboard | CO & MX |
| desempeno-hoy | dashboard | CO & MX |
| funnel-web-mx | dashboard | MX |
| docs-marketing | reference | CO & MX |

- [ ] **Step 1: Generar los 15 `meta.json`**

Para cada slug, crear `<slug>/meta.json` con `title`/`description` copiados textualmente de la card correspondiente en el `index.html` actual, el `section`/`country` de la tabla, un `order` incremental (10, 20, 30…) y **sin** campo `query`. Ejemplo (`incompletos-colombia/meta.json`):
```json
{ "title": "Leads Incompletos", "description": "Análisis de leads que quedan en estado incompleto: variables faltantes, recuperación por agente, evolución por fuente y período.", "country": "CO", "section": "dashboard", "order": 10 }
```

- [ ] **Step 2: Verificar que los 15 cargan y tienen los campos requeridos**

Run:
```bash
python3 -c "
import json,glob
req={'title','description','country','section'}
n=0
for f in glob.glob('*/meta.json'):
    m=json.load(open(f)); assert req<=set(m), f'{f} falta {req-set(m)}'; assert 'query' not in m, f'{f} no debe tener query'; n+=1
print(n,'meta.json OK sin query')
"
```
Expected: `15 meta.json OK sin query`

- [ ] **Step 3: Commit**

```bash
git add */meta.json
git commit -m "feat(hub): backfill meta.json de los 15 tableros generales existentes"
```

---

### Task 7: Generar `index.html` y verificar paridad con el hub actual

**Files:**
- Modify (generado): `index.html`

- [ ] **Step 1: Guardar el set de links actuales como baseline**

Run:
```bash
grep -oE 'href="[^"]+"' index.html | grep -v back-link | sort -u > /tmp/hub_links_before.txt
wc -l /tmp/hub_links_before.txt
```

- [ ] **Step 2: Regenerar el hub**

Run: `python3 scripts/build_hub.py`
Expected: `index.html regenerado (NNNN bytes)`

- [ ] **Step 3: Verificar paridad de contenido (cada tablero existente + externos siguen presentes)**

Run:
```bash
python3 -c "
import glob,json,re
html=open('index.html').read()
# slugs internos
for f in glob.glob('*/meta.json'):
    slug=f.split('/')[0]
    assert f'{slug}/' in html, f'falta card de {slug}'
# externos
for c in json.load(open('hub.config.json'))['external_cards']:
    assert c['url'] in html, f'falta externo {c[\"url\"]}'
print('paridad OK: 15 internos + 2 externos presentes')
"
```
Expected: `paridad OK: 15 internos + 2 externos presentes`

- [ ] **Step 4: Smoke test visual local**

Run: `python3 -m http.server 8765 >/dev/null 2>&1 & sleep 1; curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8765/; kill %1`
Expected: `200` (y abrir en navegador para confirmar que General sale arriba y el tema se ve igual)

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(hub): regenerar index.html con build_hub (paridad con hub actual)"
```

---

## Phase 2 — Cron aditivo (auto-discovery de queries)

### Task 8: `run_queries.py` — descubrimiento y defaults

**Files:**
- Create: `scripts/run_queries.py`
- Test: `scripts/tests/test_run_queries.py`
- Create: `scripts/tests/fixtures/mini_repo/canales/sebastian-ciendua/cpa-diario/query.sql`

- [ ] **Step 1: Crear el fixture de query**

`scripts/tests/fixtures/mini_repo/canales/sebastian-ciendua/cpa-diario/query.sql`:
```sql
SELECT 1 AS uno
```

- [ ] **Step 2: Escribir el test que falla**

```python
# scripts/tests/test_run_queries.py
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_queries

REPO = Path(__file__).parent / "fixtures" / "mini_repo"

def test_discover_jobs_only_with_query():
    jobs = run_queries.discover_jobs(REPO)
    slugs = {j["slug"] for j in jobs}
    assert "cpa-diario" in slugs           # tiene query
    assert "incompletos-colombia" not in slugs   # NO tiene query → se ignora

def test_job_applies_default_max_bytes():
    job = next(j for j in run_queries.discover_jobs(REPO) if j["slug"] == "cpa-diario")
    assert job["max_bytes"] == run_queries.DEFAULT_MAX_BYTES   # 5 GB
    assert job["data_path"].name == "data.json"
    assert job["sql_path"].name == "query.sql"
```

- [ ] **Step 3: Correr, verificar falla**

Run: `python3 -m pytest scripts/tests/test_run_queries.py -v`
Expected: FAIL (`No module named 'run_queries'` / `has no attribute 'discover_jobs'`)

- [ ] **Step 4: Implementar descubrimiento**

```python
# scripts/run_queries.py
import json, subprocess, sys
from pathlib import Path

DEFAULT_MAX_BYTES = 5_000_000_000  # 5 GB
IGNORE_DIRS = {".git", ".github", "scripts", "docs", "node_modules"}

def discover_jobs(repo_root: Path):
    """Tableros que declaran `query` en su meta.json (o tienen build.py)."""
    repo_root = Path(repo_root)
    jobs = []
    for meta_path in sorted(repo_root.rglob("meta.json")):
        folder = meta_path.parent
        rel = folder.relative_to(repo_root)
        if rel.parts and rel.parts[0] in IGNORE_DIRS:
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        build_py = folder / "build.py"
        if not meta.get("query") and not build_py.exists():
            continue
        jobs.append({
            "slug": folder.name,
            "folder": folder,
            "sql_path": folder / meta["query"] if meta.get("query") else None,
            "data_path": folder / meta.get("data", "data.json"),
            "max_bytes": meta.get("maximum_bytes_billed", DEFAULT_MAX_BYTES),
            "build_py": build_py if build_py.exists() else None,
        })
    return jobs
```

- [ ] **Step 5: Correr, verificar pasa**

Run: `python3 -m pytest scripts/tests/test_run_queries.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/run_queries.py scripts/tests/test_run_queries.py scripts/tests/fixtures/
git commit -m "feat(cron): run_queries discover_jobs (solo tableros con query/build.py)"
```

---

### Task 9: `run_queries.py` — ejecución (bq), escape hatch y aislamiento de fallos

**Files:**
- Modify: `scripts/run_queries.py`
- Test: `scripts/tests/test_run_queries.py`

- [ ] **Step 1: Escribir el test que falla (construcción del comando bq, sin tocar BQ)**

```python
def test_build_bq_command_includes_guardrails():
    cmd = run_queries.build_bq_command(max_bytes=5_000_000_000, project="papyrus-data")
    assert cmd[0] == "bq"
    assert "--maximum_bytes_billed=5000000000" in cmd
    assert "--format=json" in cmd
    assert "--nouse_legacy_sql" in cmd
    assert "--project_id=papyrus-data" in cmd
```

- [ ] **Step 2: Correr, verificar falla**

Run: `python3 -m pytest scripts/tests/test_run_queries.py::test_build_bq_command_includes_guardrails -v`
Expected: FAIL (`has no attribute 'build_bq_command'`)

- [ ] **Step 3: Implementar ejecución**

```python
def build_bq_command(max_bytes: int, project: str):
    return [
        "bq", "query", "--nouse_legacy_sql", "--format=json",
        f"--maximum_bytes_billed={max_bytes}", f"--project_id={project}",
    ]

def run_job(job: dict, project: str) -> bool:
    """Corre un job; True si tuvo éxito. Aísla fallos (no levanta excepción)."""
    try:
        if job["build_py"]:
            subprocess.run([sys.executable, "build.py"], cwd=job["folder"], check=True, timeout=600)
        else:
            sql = job["sql_path"].read_text(encoding="utf-8")
            cmd = build_bq_command(job["max_bytes"], project)
            out = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=600)
            if out.returncode != 0:
                print(f"  ✗ {job['slug']}: {out.stderr.strip()[:300]}", file=sys.stderr)
                return False
            job["data_path"].write_text(out.stdout, encoding="utf-8")
        print(f"  ✓ {job['slug']}")
        return True
    except Exception as e:
        print(f"  ✗ {job['slug']}: {e}", file=sys.stderr)
        return False

def main():
    import os
    repo = Path(__file__).resolve().parents[1]
    project = os.environ.get("GCP_PROJECT", "papyrus-data")
    jobs = discover_jobs(repo)
    print(f"Auto-discovery: {len(jobs)} job(s)")
    ok = sum(run_job(j, project) for j in jobs)
    print(f"Hecho: {ok}/{len(jobs)} OK")
    # No fallamos el step aunque algún job falle (aislamiento).

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Correr, verificar pasa**

Run: `python3 -m pytest scripts/tests/test_run_queries.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add scripts/run_queries.py scripts/tests/test_run_queries.py
git commit -m "feat(cron): run_queries ejecución bq + escape hatch build.py + aislamiento"
```

---

### Task 10: Enganchar al workflow `update-data.yml`

**Files:**
- Modify: `.github/workflows/update-data.yml`

- [ ] **Step 1: Leer el workflow actual para ubicar el step de commit final**

Run: `cat .github/workflows/update-data.yml`
Identificar: el bloque de auth a GCP, los steps a-medida existentes, y el step final de `git add … && git commit && git push`.

- [ ] **Step 2: Agregar el step de auto-discovery ANTES del commit final**

Insertar (después de los pasos a-medida existentes, antes del commit):
```yaml
      - name: Auto-discovery — correr queries de tableros nuevos
        if: always()
        run: python3 scripts/run_queries.py

      - name: Regenerar el hub (index.html)
        if: always()
        run: python3 scripts/build_hub.py
```

- [ ] **Step 3: Asegurar que el commit final incluye los archivos generados**

En el step de commit, ampliar el `git add` para cubrir los nuevos data files y el hub:
```yaml
      - name: Commit y push de datos + hub
        if: always()
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --staged --quiet || git commit -m "data: refresh $(date -u +%FT%TZ)"
          git push
```

- [ ] **Step 4: Cambiar el push para usar el PAT de Camilo (bypass de branch protection)**

En el `actions/checkout` del job, usar un secret `HUB_PUSH_TOKEN` (PAT de Camilo, admin) en vez del `GITHUB_TOKEN`:
```yaml
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.HUB_PUSH_TOKEN }}
```
> Nota operativa (no es código): crear el PAT de Camilo con scope `repo` + `workflow` y cargarlo como secret:
> `gh secret set HUB_PUSH_TOKEN -R camilootoya-habi/tableros-marketing-habi`
> Esto se hace recién en la Task 12 (junto con branch protection), pero el YAML ya queda listo.

- [ ] **Step 5: Validar sintaxis YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/update-data.yml')); print('yaml ok')"`
Expected: `yaml ok` (si falta pyyaml: `pip install pyyaml`)

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/update-data.yml
git commit -m "feat(cron): auto-discovery + regen hub + push con PAT en update-data.yml"
```

---

## Phase 3 — Gobernanza + onboarding

### Task 11: CODEOWNERS, CONTRIBUTING.md y plantilla de tablero

**Files:**
- Create: `.github/CODEOWNERS`
- Create: `CONTRIBUTING.md`
- Create: `scripts/templates/dashboard.html`

- [ ] **Step 1: Crear `.github/CODEOWNERS`**

```
# Archivos compartidos: requieren review de Camilo
/index.html            @camilootoya-habi
/hub.config.json       @camilootoya-habi
/scripts/              @camilootoya-habi
/.github/              @camilootoya-habi
# Cada líder es dueño de su carpeta
/canales/sebastian-ciendua/   @sebastianciendua-habi
```

- [ ] **Step 2: Crear `scripts/templates/dashboard.html`**

HTML mínimo con el tema visual estándar + favicon 📢 + back-link al hub + un `fetch('data.json')` de ejemplo que pinta una tabla. (Copiar el `<head>`/`<style>` base de un tablero simple existente, p. ej. `incompletos-colombia/index.html`, y dejar un `<script>` que hace `const data = await (await fetch('data.json')).json();` y renderiza.)

- [ ] **Step 3: Crear `CONTRIBUTING.md`**

Documentar el flujo del spec §"Flujo repetible para un líder":
```markdown
# Cómo agregar tu tablero (líderes de canal)

1. `git pull && git checkout -b <tu-nombre>/<slug-del-tablero>`
2. Copia la plantilla:
   `cp -r scripts/templates/dashboard.html canales/<tu-carpeta>/<slug>/index.html`
3. Crea `canales/<tu-carpeta>/<slug>/meta.json`:
   { "title": "...", "description": "...", "country": "CO", "section": "dashboard", "order": 1, "query": "query.sql" }
4. Escribe `query.sql` y pruébalo en BigQuery con TUS credenciales.
   El resultado de `bq query --format=json` es lo que tu index.html leerá como data.json.
5. `git push` y abre un Pull Request.
6. Camilo revisa el query (costo/correctitud) y mergea.
7. El cron corre tu query → data.json, regenera el hub → tu card aparece y se actualiza a diario.

⚠️ NO edites `index.html` (raíz): es generado por `scripts/build_hub.py`.
⚠️ Tope de costo por query: 5 GB (`maximum_bytes_billed`). Súbelo en tu meta.json solo si lo justificas.
```

- [ ] **Step 4: Verificar que el generador no rompe con CODEOWNERS/template presentes**

Run: `python3 scripts/build_hub.py && python3 -m pytest scripts/tests/ -v`
Expected: regenera ok + tests PASS

- [ ] **Step 5: Commit**

```bash
git add .github/CODEOWNERS CONTRIBUTING.md scripts/templates/dashboard.html
git commit -m "feat(gov): CODEOWNERS, CONTRIBUTING y plantilla de tablero"
```

---

### Task 12: Branch protection + PAT del cron (operativo, vía gh)

**Files:** ninguno (configuración remota).

> Estos pasos los corre Camilo/Jean-Claude con la cuenta `camilootoya-habi` activa. Se hacen al final, cuando la rama ya esté mergeada a `main` (si no, branch protection bloquearía el propio merge del PR de esta feature; ver Task 13).

- [ ] **Step 1: Crear y cargar el PAT del cron**

Crear un PAT (classic) de Camilo con scope `repo` + `workflow`, luego:
Run: `gh secret set HUB_PUSH_TOKEN -R camilootoya-habi/tableros-marketing-habi`
(pegar el token cuando lo pida)

- [ ] **Step 2: Activar branch protection en `main` (sin incluir admins)**

El API de branch protection exige un body JSON anidado con todas las claves
top-level presentes; `gh api -F` no arma JSON anidado, así que se manda por stdin:
```bash
echo '{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "require_code_owner_reviews": true
  },
  "restrictions": null
}' | gh api -X PUT repos/camilootoya-habi/tableros-marketing-habi/branches/main/protection \
      -H "Accept: application/vnd.github+json" --input -
```
Expected: JSON con `"enforce_admins": {"enabled": false}` → Camilo (admin) pasa directo, líderes por PR.

- [ ] **Step 3: Verificar**

Run: `gh api repos/camilootoya-habi/tableros-marketing-habi/branches/main/protection --jq '{admins:.enforce_admins.enabled, reviews:.required_pull_request_reviews.required_approving_review_count, codeowners:.required_pull_request_reviews.require_code_owner_reviews}'`
Expected: `{"admins":false,"reviews":1,"codeowners":true}`

- [ ] **Step 4: Confirmar que el cron pushea (disparo manual)**

Run: `gh workflow run update-data.yml -R camilootoya-habi/tableros-marketing-habi` y verificar que termina `success` y commitea (ver `gh run list`).
Expected: run `completed/success` + nuevo commit `data: refresh …` en `main`.

---

### Task 13: Piloto Sebastián + merge de la feature

**Files:**
- Create: `canales/sebastian-ciendua/_leader.json`

- [ ] **Step 1: Crear el registro del líder**

`canales/sebastian-ciendua/_leader.json`:
```json
{ "name": "Sebastián Ciendua", "channel": "Performance Colombia", "order": 1 }
```

- [ ] **Step 2: Regenerar el hub (debe seguir sin la sección de Sebastián hasta que tenga un tablero)**

Run: `python3 scripts/build_hub.py`
Expected: el hub NO muestra sección de Sebastián todavía (no tiene cards) — confirmar que `build_page` omite líderes sin tableros.

- [ ] **Step 3: Commit + push de la rama y abrir PR de la feature**

```bash
git add canales/sebastian-ciendua/_leader.json index.html
git commit -m "feat(hub): registrar líder piloto Sebastián Ciendua (Performance Colombia)"
git push -u origin hub-multilider
gh pr create -R camilootoya-habi/tableros-marketing-habi --fill --base main --head hub-multilider
```

- [ ] **Step 4: Mergear la feature a `main` (antes de activar branch protection — Task 12)**

Camilo revisa y mergea el PR. Recién después correr la Task 12 (branch protection), para no bloquear este propio merge.

- [ ] **Step 5: Entregar a Sebastián**

Compartir `CONTRIBUTING.md` y la plantilla; él monta su primer tablero (`canales/sebastian-ciendua/<slug>/` con `meta.json` + `query.sql`) por el flujo de PR como prueba end-to-end.

---

## Notas de orden de ejecución

- Tasks 1–11 y 13 (excepto activar protección) se hacen en la rama `hub-multilider`.
- **Task 12 (branch protection) va de último**, después de mergear la feature, o bloquearía el merge del propio PR.
- El secret `HUB_PUSH_TOKEN` debe existir antes de que el cron vuelva a correr tras activar branch protection.
