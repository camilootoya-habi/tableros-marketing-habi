# Unificar los análisis en el monorepo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Traer los 2 análisis (postmortems) que viven en repos separados al monorepo del hub como tableros in-repo con `section: analysis`, y borrar los repos standalone.

**Architecture:** Cada análisis pasa a ser una carpeta en la raíz del hub (dueño `general`) con su `index.html` (copiado tal cual) + un `meta.json`. Se vacían los `external_cards` de `hub.config.json` y el generador (`build_hub.py`) los toma como cards in-repo. Son estáticos → sin impacto en el cron.

**Tech Stack:** Python 3 (generador existente), GitHub Pages, `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-05-26-unificar-analisis-design.md`

**Rama:** `unificar-analisis` (ya creada).

---

## File Structure

- Create: `analisis-asignados-co/index.html` (copia) + `analisis-asignados-co/meta.json`
- Create: `analisis-mty-multimedios/index.html` (copia) + `analisis-mty-multimedios/meta.json`
- Modify: `hub.config.json` (vaciar `external_cards`)
- Modify (generado): `index.html`
- Modify: `CLAUDE.md`, `README.md` (mención de análisis in-repo)

Fuente de los HTML: los clones locales ya re-homeados en `~/habi/analisis-asignados-co/index.html` y `~/habi/analisis-mty-multimedios/index.html`.

---

### Task 1: Traer los 2 análisis al monorepo (carpetas + meta.json + back-link relativo)

**Files:**
- Create: `analisis-asignados-co/index.html`, `analisis-asignados-co/meta.json`
- Create: `analisis-mty-multimedios/index.html`, `analisis-mty-multimedios/meta.json`

- [ ] **Step 1: Copiar los index.html desde los clones locales**

```bash
cd /home/administrador/habi/tableros-marketing
mkdir -p analisis-asignados-co analisis-mty-multimedios
cp ~/habi/analisis-asignados-co/index.html analisis-asignados-co/index.html
cp ~/habi/analisis-mty-multimedios/index.html analisis-mty-multimedios/index.html
```

- [ ] **Step 2: Relativizar el back-link al hub en ambos**

El back-link hoy es la URL absoluta del hub. Reemplazar el `href` absoluto por `../`:
```bash
cd /home/administrador/habi/tableros-marketing
sed -i 's#href="https://camilootoya-habi.github.io/tableros-marketing-habi/"#href="../"#g' \
  analisis-asignados-co/index.html analisis-mty-multimedios/index.html
```
Verificar que quedó el relativo y NO quedó el absoluto:
```bash
grep -c 'href="../"' analisis-asignados-co/index.html analisis-mty-multimedios/index.html
grep -c 'camilootoya-habi.github.io/tableros-marketing-habi' analisis-asignados-co/index.html analisis-mty-multimedios/index.html
```
Expected: el primero ≥1 en cada archivo; el segundo `0` en cada archivo. (Si el segundo no es 0, hay otra ocurrencia de la URL — revísala manualmente; debe ser solo el back-link.)

- [ ] **Step 3: Crear `analisis-asignados-co/meta.json`**

```json
{ "title": "Análisis de asignados — 2026", "description": "Postmortem de la caída de asignados desde el 12 de marzo: nuevo Backbone, recalibración de metas y plan para recuperar volumen.", "country": "CO", "section": "analysis", "order": 1 }
```

- [ ] **Step 4: Crear `analisis-mty-multimedios/meta.json`**

```json
{ "title": "Postmortem campaña Multimedios — MTY", "description": "Impacto de la campaña ALL-IN TUHABI en Monterrey, marzo 2026: tráfico, registros, conversión y funnel comercial.", "country": "MX", "section": "analysis", "order": 2 }
```

- [ ] **Step 5: Verificar que el generador los descubre como `general` / `analysis`**

```bash
cd /home/administrador/habi/tableros-marketing
python3 -c "
import sys; sys.path.insert(0,'scripts'); import build_hub
ds = {d['slug']: d for d in build_hub.discover_dashboards('.')}
for s in ('analisis-asignados-co','analisis-mty-multimedios'):
    d = ds[s]; assert d['owner']=='general' and d['section']=='analysis' and d['link']==s+'/', d
    print('OK', s, d['link'])
"
```
Expected: `OK analisis-asignados-co analisis-asignados-co/` y `OK analisis-mty-multimedios analisis-mty-multimedios/`

- [ ] **Step 6: Commit**

```bash
cd /home/administrador/habi/tableros-marketing
git add analisis-asignados-co analisis-mty-multimedios
git commit -m "feat(hub): traer los 2 análisis al monorepo (in-repo, section analysis)"
```

---

### Task 2: Vaciar `external_cards`, regenerar el hub y verificar paridad

**Files:**
- Modify: `hub.config.json`
- Modify (generado): `index.html`

- [ ] **Step 1: Vaciar `external_cards` en `hub.config.json`**

Dejar el resto del archivo igual; solo cambiar el valor de `external_cards` a `[]`. Resultado:
```json
{
  "title": "Growth & Marketing",
  "subtitle": "Lo que no se mide no se mejora — y acá buscamos mejora continua.",
  "general": { "title": "General · Marketing", "order": 0 },
  "external_cards": []
}
```
Validar JSON:
```bash
cd /home/administrador/habi/tableros-marketing
python3 -c "import json; assert json.load(open('hub.config.json'))['external_cards']==[]; print('external_cards vacío OK')"
```
Expected: `external_cards vacío OK`

- [ ] **Step 2: Regenerar el hub**

```bash
cd /home/administrador/habi/tableros-marketing
python3 scripts/build_hub.py
```
Expected: `index.html regenerado (...)`

- [ ] **Step 3: Verificar paridad — 17 cards, los 2 análisis ahora con `href` relativo y SIN URL externa**

```bash
cd /home/administrador/habi/tableros-marketing
python3 -c "
html = open('index.html').read()
assert html.count('class=\"card\"') == 17, html.count('class=\"card\"')
# los análisis ahora son in-repo (href relativo)
assert 'href=\"analisis-asignados-co/\"' in html
assert 'href=\"analisis-mty-multimedios/\"' in html
# ya no quedan las URLs externas a los repos standalone
assert 'github.io/analisis-asignados-co' not in html
assert 'github.io/analisis-mty-multimedios' not in html
# siguen bajo Analysis
assert '>Analysis<' in html
print('paridad OK: 17 cards, análisis in-repo, sin URLs externas')
"
```
Expected: `paridad OK: 17 cards, análisis in-repo, sin URLs externas`

- [ ] **Step 4: Tests + smoke local de los análisis in-repo**

```bash
cd /home/administrador/habi/tableros-marketing
python3 -m pytest scripts/tests/ -q
python3 -m http.server 8771 >/dev/null 2>&1 & SRV=$!; sleep 1
for p in / /analisis-asignados-co/ /analisis-mty-multimedios/; do
  echo -n "$p -> "; curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8771$p"
done
kill $SRV 2>/dev/null
```
Expected: tests `passed`; los 3 paths dan `200`.

- [ ] **Step 5: Commit**

```bash
cd /home/administrador/habi/tableros-marketing
git add hub.config.json index.html
git commit -m "feat(hub): vaciar external_cards y regenerar (análisis ahora in-repo)"
```

---

### Task 3: Actualizar docs (CLAUDE.md, README.md)

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: Ajustar la mención de `external_cards` en `CLAUDE.md`**

Buscar la línea que describe `hub.config.json` (dice "header del hub + cards externas (informes en repos aparte)") y cambiarla a:
```
- `hub.config.json` — header del hub + `external_cards` (links a dashboards GENUINAMENTE externos; hoy vacío — los análisis viven in-repo como `section: analysis`).
```

- [ ] **Step 2: Ajustar `README.md`**

Si `README.md` menciona que los análisis/informes viven en repos aparte, corregirlo: los análisis viven in-repo (carpetas con `section: analysis`). Si no lo menciona, no cambiar nada.

- [ ] **Step 3: Verificar que el generador sigue OK e index.html no cambia por los docs**

```bash
cd /home/administrador/habi/tableros-marketing
python3 scripts/build_hub.py && git status -s index.html
```
Expected: `index.html regenerado (...)` y `git status -s index.html` vacío (sin cambios — CLAUDE/README no son tableros).

- [ ] **Step 4: Commit**

```bash
cd /home/administrador/habi/tableros-marketing
git add CLAUDE.md README.md
git commit -m "docs: análisis viven in-repo; external_cards solo para links externos genuinos"
```

---

### Task 4: PR, merge, verificación en vivo y borrado de repos viejos (operativo)

**Files:** ninguno (operaciones remotas).

> Estos pasos los corre Camilo/Jean-Claude con la cuenta `camilootoya-habi` activa.
> El borrado de repos es **irreversible** — solo tras confirmar las URLs in-repo en vivo.

- [ ] **Step 1: Push de la rama + abrir PR**

```bash
cd /home/administrador/habi/tableros-marketing
git push -u origin unificar-analisis
gh pr create -R camilootoya-habi/tableros-marketing-habi --base main --head unificar-analisis \
  --title "Unificar los análisis en el monorepo" --fill
```

- [ ] **Step 2: Mergear el PR**

```bash
gh pr merge -R camilootoya-habi/tableros-marketing-habi --merge --delete-branch
```
Luego sincronizar local: `git checkout main && git pull --ff-only origin main`.

- [ ] **Step 3: Esperar el build de Pages y verificar las URLs in-repo EN VIVO**

```bash
sleep 60
for p in tableros-marketing-habi/analisis-asignados-co/ tableros-marketing-habi/analisis-mty-multimedios/; do
  echo -n "$p -> "; curl -s -o /dev/null -w "%{http_code}\n" "https://camilootoya-habi.github.io/$p"
done
```
Expected: ambos `200`. (Si dan 404, esperar otro minuto y reintentar — Pages aún construyendo. NO borrar los repos hasta ver 200.)

- [ ] **Step 4: Borrar los 2 repos standalone (irreversible — solo tras 200 en Step 3)**

```bash
gh repo delete camilootoya-habi/analisis-asignados-co --yes
gh repo delete camilootoya-habi/analisis-mty-multimedios --yes
```
(Requiere scope `delete_repo` en el token de `camilootoya-habi`. Si `gh` lo rechaza por permisos, hacerlo desde la web: Settings → Danger Zone → Delete, o `gh auth refresh -s delete_repo`.)

- [ ] **Step 5: Verificar el cierre**

```bash
gh repo view camilootoya-habi/analisis-asignados-co 2>&1 | head -1   # debe dar "Not Found"
gh repo view camilootoya-habi/analisis-mty-multimedios 2>&1 | head -1 # debe dar "Not Found"
```
Expected: ambos "Not Found".

---

## Nota fuera del PR: memoria

Tras el merge, actualizar la memoria de Jean-Claude (no es parte del repo):
- `habi/references.md` y `habi/tableros/general.md`: los análisis ya no son repos satélite; viven in-repo en `analisis-asignados-co/` y `analisis-mty-multimedios/`. Quedan solo 1 repo (el hub) para todo marketing.
