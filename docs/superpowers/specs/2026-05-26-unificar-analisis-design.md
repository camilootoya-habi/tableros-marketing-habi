# Unificar los análisis en el monorepo — Diseño

- **Fecha:** 2026-05-26
- **Estado:** Aprobado (pendiente plan de implementación)
- **Repo:** `camilootoya-habi/tableros-marketing-habi`
- **Base:** modelo multi-líder generado (ver `2026-05-26-hub-multilider-design.md`)

## Contexto

Hoy los dashboards y reference viven en el monorepo del hub, pero los 2 **análisis**
(postmortems) viven en repos **separados** y se enlazan desde el hub como
`external_cards` en `hub.config.json`:
- `camilootoya-habi/analisis-asignados-co` → card "Análisis de asignados — 2026"
- `camilootoya-habi/analisis-mty-multimedios` → card "Postmortem campaña Multimedios — MTY"

Ambos son un **único `index.html` autocontenido** (~88K / ~72K, sin assets, sin
data, sin pipeline de cron).

El usuario quiere que **todo viva en un mismo repo**.

## Objetivos

1. Traer los 2 análisis al monorepo como tableros de primera clase con
   `section: analysis` (dueño `general`).
2. Que el hub los enlace **in-repo** (rutas relativas), no a repos externos.
3. Dejar la convención: futuros análisis viven in-repo, no en repos separados.

## No-objetivos (YAGNI)

- **No** preservar el historial git de los repos standalone (es trivial y los
  repos se borran). Copia simple del `index.html`.
- **No** eliminar el mecanismo `external_cards`: se vacía pero se conserva para
  enlaces genuinamente externos a futuro (p. ej. un Looker/Data Studio).
- **No** tocar el cron ni los pipelines a-medida (los análisis son estáticos).

## Decisión tomada (brainstorming)

- **Repos viejos**: se **borran** tras verificar la versión in-repo en vivo. Sus
  URLs `*.github.io/analisis-*` mueren. Riesgo bajo: esas URLs se crearon hoy en
  la migración, sin bookmarks consolidados; el hub apuntará a la versión in-repo.

## Diseño

### 1. Contenido que se mueve
Carpetas nuevas en la **raíz** (dueño `general`):
```
analisis-asignados-co/
├── index.html      ← copiado tal cual del repo standalone
└── meta.json
analisis-mty-multimedios/
├── index.html      ← copiado tal cual
└── meta.json
```

`analisis-asignados-co/meta.json`:
```json
{ "title": "Análisis de asignados — 2026",
  "description": "Postmortem de la caída de asignados desde el 12 de marzo: nuevo Backbone, recalibración de metas y plan para recuperar volumen.",
  "country": "CO", "section": "analysis", "order": 1 }
```

`analisis-mty-multimedios/meta.json`:
```json
{ "title": "Postmortem campaña Multimedios — MTY",
  "description": "Impacto de la campaña ALL-IN TUHABI en Monterrey, marzo 2026: tráfico, registros, conversión y funnel comercial.",
  "country": "MX", "section": "analysis", "order": 2 }
```
(título/descripción/país/order = los mismos valores que los `external_cards`
actuales, para conservar paridad). Sin `query` → estáticos.

### 2. Hub
- Quitar las 2 entradas de `external_cards` en `hub.config.json` → queda `[]`.
- `python3 scripts/build_hub.py` regenera `index.html`: las 2 cards de análisis
  ahora apuntan a rutas relativas (`analisis-asignados-co/`, `analisis-mty-multimedios/`)
  bajo **General › Analysis**, mismo orden. El resto del hub no cambia.

### 3. Back-links internos
- Dentro de cada análisis, el `← Hub` es hoy una URL **absoluta** al hub. Se
  relativiza a `../` (consistente con los demás tableros e independiente del host).
  Desde `tableros-marketing-habi/analisis-asignados-co/`, `../` = raíz del hub.

### 4. Borrar repos standalone
Tras mergear y verificar que `…/tableros-marketing-habi/analisis-asignados-co/` y
`…/analisis-mty-multimedios/` sirven en vivo (HTTP 200):
```
gh repo delete camilootoya-habi/analisis-asignados-co --yes
gh repo delete camilootoya-habi/analisis-mty-multimedios --yes
```
(Operativo, al final; irreversible.)

### 5. Docs y memoria
- `CLAUDE.md` / `README.md`: ajustar la mención de que los análisis viven in-repo;
  `external_cards` queda solo para enlaces externos genuinos.
- Memoria (`habi/references.md`, `habi/tableros/general.md`): los análisis ya no
  son repos satélite; viven en el hub.

## Verificación

- `python3 -m pytest scripts/tests/` sigue verde.
- Hub regenerado: 17 cards, los 2 análisis ahora con `href` relativo (no URL externa).
- Local: `python3 -m http.server` → abrir `/analisis-asignados-co/` y
  `/analisis-mty-multimedios/` y el `← Hub` regresa al hub.
- Post-merge en vivo: ambas URLs in-repo dan HTTP 200 **antes** de borrar los repos viejos.

## Fases de implementación (alto nivel; detalle en el plan)

1. Crear las 2 carpetas con `index.html` (copiado) + `meta.json`; relativizar back-links.
2. Vaciar `external_cards`; regenerar `index.html`; verificar paridad + tests.
3. Actualizar docs (CLAUDE.md/README) + memoria.
4. Rama → PR → merge → verificar URLs in-repo en vivo → **borrar los 2 repos viejos**.
