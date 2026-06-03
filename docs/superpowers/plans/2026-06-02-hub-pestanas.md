# Hub — Pestañas en el panel principal · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Añadir una barra de 5 pestañas (Marketing General · Performance/Growth × CO/MX) al hub generado; todo el contenido actual cae en Marketing General y las otras 4 muestran "próximamente".

**Architecture:** El cambio vive 100% en `scripts/build_hub.py` (lógica de asignación + render) y `scripts/templates/hub.html` (barra, paneles, JS). `index.html` se regenera. Las pestañas se definen en `hub.config.json`; el tab de cada tablero se deriva del dueño/canal con override opcional `tab` en `meta.json`.

**Tech Stack:** Python 3 (stdlib `json`, `html`, `unicodedata`), HTML/CSS/JS vanilla, pytest.

---

## File Structure

- `scripts/build_hub.py` — añade `slugify`, `resolve_tab`, `render_empty_panel`; `discover_dashboards` lee `tab`; `build_page` agrupa por pestaña y arma barra + paneles.
- `scripts/templates/hub.html` — barra `.tabs`, paneles `.tab-panel`, CSS y JS de cambio de pestaña.
- `hub.config.json` — nuevo arreglo `tabs`.
- `scripts/tests/test_build_hub.py` — tests de slug, resolución de tab, barra, estado vacío.

---

### Task 1: Helper `slugify` y `resolve_tab`

**Files:**
- Modify: `scripts/build_hub.py`
- Test: `scripts/tests/test_build_hub.py`

- [ ] **Step 1: Test que falla**

```python
def test_slugify_strips_accents_and_spaces():
    assert build_hub.slugify("Performance Colombia") == "performance-colombia"
    assert build_hub.slugify("Growth México") == "growth-mexico"

def test_resolve_tab_priority():
    leaders = {"sebastian-ciendua": {"channel": "Performance Colombia"}}
    # override explícito gana
    assert build_hub.resolve_tab({"owner": "general", "tab": "growth-mexico"}, leaders) == "growth-mexico"
    # general sin override → marketing-general
    assert build_hub.resolve_tab({"owner": "general", "tab": None}, leaders) == "marketing-general"
    # líder → slug de su channel
    assert build_hub.resolve_tab({"owner": "sebastian-ciendua", "tab": None}, leaders) == "performance-colombia"
```

- [ ] **Step 2: Correr y ver fallar**

Run: `python3 -m pytest scripts/tests/test_build_hub.py -k "slugify or resolve_tab" -q`
Expected: FAIL (`AttributeError: module 'build_hub' has no attribute 'slugify'`)

- [ ] **Step 3: Implementar**

En `scripts/build_hub.py`, tras los imports añadir `import unicodedata` y:

```python
def slugify(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return "-".join(norm.lower().split())


def resolve_tab(dashboard: dict, leaders: dict) -> str:
    if dashboard.get("tab"):
        return dashboard["tab"]
    if dashboard["owner"] == "general":
        return "marketing-general"
    channel = leaders.get(dashboard["owner"], {}).get("channel", "")
    return slugify(channel) if channel else "marketing-general"
```

- [ ] **Step 4: Correr y ver pasar**

Run: `python3 -m pytest scripts/tests/test_build_hub.py -k "slugify or resolve_tab" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/build_hub.py scripts/tests/test_build_hub.py
git commit -m "feat(hub): slugify + resolve_tab para asignar tableros a pestañas"
```

---

### Task 2: `discover_dashboards` lee el campo `tab`

**Files:**
- Modify: `scripts/build_hub.py`
- Test: `scripts/tests/test_build_hub.py`

- [ ] **Step 1: Test que falla**

```python
def test_discover_dashboards_includes_tab_key():
    dashboards = build_hub.discover_dashboards(REPO)
    by_slug = {d["slug"]: d for d in dashboards}
    # el fixture no declara tab → None (se derivará después)
    assert by_slug["incompletos-colombia"]["tab"] is None
```

- [ ] **Step 2: Correr y ver fallar**

Run: `python3 -m pytest scripts/tests/test_build_hub.py -k discover_dashboards_includes_tab -q`
Expected: FAIL (`KeyError: 'tab'`)

- [ ] **Step 3: Implementar**

En el dict que arma `discover_dashboards`, añadir `"tab": meta.get("tab")`.

- [ ] **Step 4: Correr y ver pasar**

Run: `python3 -m pytest scripts/tests/test_build_hub.py -k discover_dashboards_includes_tab -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/build_hub.py scripts/tests/test_build_hub.py
git commit -m "feat(hub): discover_dashboards expone el campo tab del meta"
```

---

### Task 3: `build_page` agrupa por pestaña + barra + paneles + estado vacío

**Files:**
- Modify: `scripts/build_hub.py`, `scripts/templates/hub.html`
- Test: `scripts/tests/test_build_hub.py`

- [ ] **Step 1: Tests que fallan**

```python
TABS = [
    {"id": "marketing-general", "label": "Marketing General", "order": 0},
    {"id": "performance-colombia", "label": "Performance Colombia", "order": 1},
    {"id": "growth-mexico", "label": "Growth Mexico", "order": 2},
]

def _cfg():
    return {"title": "T", "subtitle": "s", "general": {"title": "General · Marketing", "order": 0},
            "external_cards": [], "tabs": TABS}

def test_tab_bar_renders_all_tabs_in_order():
    html = build_hub.build_page(build_hub.discover_dashboards(REPO), build_hub.discover_leaders(REPO), _cfg(), build_hub.load_template())
    assert html.index('data-tab="marketing-general"') < html.index('data-tab="performance-colombia"') < html.index('data-tab="growth-mexico"')
    assert "Marketing General" in html and "Growth Mexico" in html

def test_general_dashboards_land_in_marketing_general_panel():
    html = build_hub.build_page(build_hub.discover_dashboards(REPO), build_hub.discover_leaders(REPO), _cfg(), build_hub.load_template())
    panel = html.split('id="panel-marketing-general"')[1].split('id="panel-')[0]
    assert "incompletos-colombia/" in panel

def test_leader_dashboard_lands_in_channel_panel():
    html = build_hub.build_page(build_hub.discover_dashboards(REPO), build_hub.discover_leaders(REPO), _cfg(), build_hub.load_template())
    panel = html.split('id="panel-performance-colombia"')[1].split('id="panel-')[0]
    assert "cpa-diario/" in panel

def test_empty_tab_shows_coming_soon():
    html = build_hub.build_page(build_hub.discover_dashboards(REPO), build_hub.discover_leaders(REPO), _cfg(), build_hub.load_template())
    panel = html.split('id="panel-growth-mexico"')[1].split('id="panel-')[0]
    assert "Próximamente" in panel
```

- [ ] **Step 2: Correr y ver fallar**

Run: `python3 -m pytest scripts/tests/test_build_hub.py -k "tab_bar or _panel or coming_soon" -q`
Expected: FAIL (paneles/atributos inexistentes)

- [ ] **Step 3: Implementar en `build_hub.py`**

Reescribir `build_page` (y añadir helpers de render). Mantener `render_owner_block`/`render_card` intactos.

```python
DEFAULT_TABS = [{"id": "marketing-general", "label": "Marketing General", "order": 0}]


def render_empty_panel() -> str:
    return ('    <div class="empty-state">Próximamente — aún no hay tableros en '
            'esta sección.</div>')


def render_tab_content(tab_id, dashboards, leaders, config) -> strः
    """Owner-blocks dentro de una pestaña: general primero, luego líderes por order."""
    blocks = []
    general_cards = [d for d in dashboards if d["owner"] == "general"]
    if tab_id == "marketing-general":
        general_cards = general_cards + [{**c, "link": c["url"]} for c in config.get("external_cards", [])]
    if general_cards:
        blocks.append(render_owner_block(config["general"]["title"], general_cards))
    for lid in sorted(leaders, key=lambda k: leaders[k].get("order", 9999)):
        lcards = [d for d in dashboards if d["owner"] == lid]
        if lcards:
            ld = leaders[lid]
            blocks.append(render_owner_block(f'{ld["name"]} · {ld["channel"]}', lcards))
    return "\n".join(blocks) if blocks else render_empty_panel()


def build_page(dashboards, leaders, config, template) -> str:
    tabs = sorted(config.get("tabs", DEFAULT_TABS), key=lambda t: t.get("order", 9999))
    valid_ids = {t["id"] for t in tabs}
    for d in dashboards:
        tid = resolve_tab(d, leaders)
        d["_tab"] = tid if tid in valid_ids else "marketing-general"

    tab_bar, panels = [], []
    for i, t in enumerate(tabs):
        active = " active" if i == 0 else ""
        tab_bar.append(f'    <button type="button" class="tab-btn{active}" data-tab="{escape(t["id"])}">{escape(t["label"])}</button>')
        in_tab = [d for d in dashboards if d["_tab"] == t["id"]]
        content = render_tab_content(t["id"], in_tab, leaders, config)
        panels.append(f'  <div class="tab-panel{active}" id="panel-{escape(t["id"])}">\n{content}\n  </div>')

    return (template
            .replace("{{TITLE}}", escape(config["title"]))
            .replace("{{SUBTITLE}}", escape(config["subtitle"]))
            .replace("{{TABS}}", "\n".join(tab_bar))
            .replace("{{PANELS}}", "\n".join(panels)))
```

(Corregir el typo `->str:` — la firma es `def render_tab_content(tab_id, dashboards, leaders, config) -> str:`.)

- [ ] **Step 4: Editar `scripts/templates/hub.html`**

Reemplazar la línea `{{CONTENT}}` por:

```html
  <nav class="tabs" role="tablist">
{{TABS}}
  </nav>
{{PANELS}}
```

Añadir al `<style>`:

```css
  .tabs { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-bottom: 36px; max-width: 1400px; width: 100%; }
  .tab-btn { background: var(--card); border: 1px solid var(--border); color: var(--text-muted); border-radius: 8px; padding: 8px 16px; font-size: 14px; font-weight: 600; cursor: pointer; transition: color .15s, border-color .15s, background .15s; }
  .tab-btn:hover { color: var(--accent); border-color: var(--accent); }
  .tab-btn.active { color: var(--bg); background: var(--accent); border-color: var(--accent); }
  body.light .tab-btn.active { color: #fff; }
  .tab-panel { display: none; width: 100%; max-width: 1400px; }
  .tab-panel.active { display: block; }
  .empty-state { text-align: center; color: var(--text-muted-2); font-size: 15px; padding: 64px 16px; }
```

Añadir antes de `</body>` (tras el IIFE de tema) el JS:

```html
<script>
  (function(){
    const btns = document.querySelectorAll('.tab-btn');
    const panels = document.querySelectorAll('.tab-panel');
    function show(id){
      let found = false;
      btns.forEach(b => b.classList.toggle('active', b.dataset.tab === id));
      panels.forEach(p => { const on = p.id === 'panel-' + id; p.classList.toggle('active', on); found = found || on; });
      if (found) localStorage.setItem('hub-tab', id);
      return found;
    }
    btns.forEach(b => b.addEventListener('click', () => { show(b.dataset.tab); location.hash = b.dataset.tab; }));
    const fromHash = location.hash.replace('#', '');
    if (!(fromHash && show(fromHash))) show(localStorage.getItem('hub-tab') || (btns[0] && btns[0].dataset.tab));
  })();
</script>
```

- [ ] **Step 5: Correr y ver pasar**

Run: `python3 -m pytest scripts/tests/test_build_hub.py -q`
Expected: PASS (todos). Si `test_build_page_orders_general_then_leaders` o el de external_card fallan por no traer `tabs`, ajustarlos para usar la config con `tabs` o confirmar que el fallback `DEFAULT_TABS` los mantiene verdes.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_hub.py scripts/templates/hub.html scripts/tests/test_build_hub.py
git commit -m "feat(hub): barra de pestañas con paneles por equipo y estado próximamente"
```

---

### Task 4: Definir las 5 pestañas en `hub.config.json` y regenerar

**Files:**
- Modify: `hub.config.json`, `index.html` (regenerado)

- [ ] **Step 1: Añadir el arreglo `tabs` a `hub.config.json`**

```json
{
  "title": "Growth & Marketing",
  "subtitle": "Lo que no se mide no se mejora — y acá buscamos mejora continua.",
  "general": { "title": "General · Marketing", "order": 0 },
  "external_cards": [],
  "tabs": [
    { "id": "marketing-general",    "label": "Marketing General",    "order": 0 },
    { "id": "performance-colombia", "label": "Performance Colombia", "order": 1 },
    { "id": "growth-colombia",      "label": "Growth Colombia",      "order": 2 },
    { "id": "performance-mexico",   "label": "Performance Mexico",   "order": 3 },
    { "id": "growth-mexico",        "label": "Growth Mexico",        "order": 4 }
  ]
}
```

- [ ] **Step 2: Regenerar y verificar**

Run: `python3 scripts/build_hub.py && python3 -m pytest scripts/tests/ -q`
Expected: `index.html regenerado (...)` + todos los tests PASS. Abrir `index.html` y confirmar 5 pestañas, General con el contenido de hoy, las otras 4 con "Próximamente".

- [ ] **Step 3: Commit**

```bash
git add hub.config.json index.html
git commit -m "feat(hub): activar las 5 pestañas (General + Performance/Growth CO/MX)"
```

---

## Self-Review

- **Cobertura del spec:** definición de tabs (Task 4) ✓; derivación por dueño/canal + override (Task 1) ✓; lectura de `tab` en meta (Task 2) ✓; barra + paneles + layout interno igual + estado vacío (Task 3) ✓; tests (Tasks 1-3) ✓.
- **Placeholders:** ninguno; todo el código está completo. Nota: corregir el typo `->str:` indicado en Task 3 Step 3.
- **Consistencia de tipos:** `resolve_tab(dashboard, leaders)`, `slugify(text)`, `render_tab_content(tab_id, dashboards, leaders, config)`, `render_empty_panel()`, placeholders `{{TABS}}`/`{{PANELS}}` — coherentes entre tareas.
</content>
