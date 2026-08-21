# Growth & Marketing Hub — guía para agentes

Hub de tableros de marketing/growth de Habi. Sitio **estático** en GitHub Pages, **multi-líder**.
Live: https://camilootoya-habi.github.io/tableros-marketing-habi/

## Reglas de oro (no romper)

1. **NUNCA edites el `index.html` de la raíz.** Es un artefacto **GENERADO** por `scripts/build_hub.py`; cualquier cambio a mano se borra en el próximo build. Para cambiar el hub, edita los `meta.json` / `hub.config.json` y corre `python3 scripts/build_hub.py`.
2. **Si eres el agente de un líder de canal: NUNCA pushees a `main`.** Trabaja en una rama y abre un **Pull Request**. Solo Camilo (`@camilootoya-habi`) revisa y mergea. (Hoy no hay branch protection que lo impida — respétalo por convención.)
3. No toques los pipelines a-medida del cron en `.github/workflows/update-data.yml` salvo que sepas exactamente lo que haces.
4. **El cierre son SIEMPRE dos líneas de negocio, y NO son el mismo evento.** `oportunidad_del_negocio='Cierre - Comprado'` es compra directa (transacción cerrada); `oportunidad_inmobiliaria='Contrato firmado'` es una **captación** de la red de aliados (mandato firmado, no venta: de los 29 del loop, 0 tienen fecha de publicación o de venta). Hay que sumarlas —contar solo la primera reportaba 9 de 38 cierres en Colombia— pero al presentar el número afuera hay que decir la composición. Antes de escribir o editar cualquier query de cierres, lee `marketing-loop/METRICAS.md`.

## Estructura

- `<slug>/` (en la raíz) = tableros **generales** de Camilo (dueño `general`).
- `canales/<lider>/<slug>/` = tableros de un **líder de canal**; `canales/<lider>/_leader.json` registra `{name, channel, order}`.
- Cada tablero = una carpeta con:
  - `meta.json` (**obligatorio**) — metadata de la card.
  - `index.html` — el tablero (hace `fetch('data.json')`).
  - `query.sql` (opcional) — si existe, el cron lo corre y escribe `data.json`.
  - `data.json` — generado por el cron (no se edita a mano).
- `hub.config.json` — header del hub + `external_cards` (links a dashboards GENUINAMENTE externos; hoy vacío — los análisis viven in-repo como `section: analysis`).
- `scripts/build_hub.py` — regenera `index.html`. `scripts/run_queries.py` — auto-discovery de queries en el cron. `scripts/templates/` — plantillas (`hub.html`, `dashboard.html`).

El **dueño** se infiere por ubicación: carpeta en la raíz = `general`; bajo `canales/<lider>/` = ese líder. El hub muestra la sección General arriba y una sección inline por líder debajo (líderes sin tableros se omiten).

## Contrato de `meta.json`

```json
{ "title": "...", "description": "...", "country": "CO",
  "section": "dashboard", "order": 10, "query": "query.sql",
  "maximum_bytes_billed": 5000000000 }
```
- `section`: `dashboard` | `analysis` | `reference` (sub-grupo dentro del dueño).
- `order`: menor = más arriba en su sección. Tableros nuevos → `order` mayor (quedan al final, orden cronológico).
- `query` / `maximum_bytes_billed`: opcionales. Sin `query` = tablero estático (el cron lo ignora, pero igual sale su card). Tope de costo por query: 5 GB por defecto.

## Cómo agregar un tablero (líderes) → ver `CONTRIBUTING.md`

Resumen: rama → copia `scripts/templates/dashboard.html` a `canales/<tu-carpeta>/<slug>/index.html` → crea `meta.json` + `query.sql` (pruébalo en BigQuery con TUS credenciales) → `git push` + **PR** → Camilo revisa y mergea → el cron corre tu query, regenera el hub, y tu card aparece bajo tu sección, actualizándose a diario.

## Gráficas (estándar)

**Las gráficas se hacen con [Chart.js](https://www.chartjs.org/) (CDN), NO con SVG dibujado a mano.** El template ya trae el `<script>` del CDN y un helper `mkChart(id, labels, data, {type, pct, color})` con tooltips, ejes y grilla temáticos (claro/oscuro). Patrón: un `<canvas>` dentro de `.panel > .ch`. Referencia de estilo: los tableros `marketing-loop` y `funnel-nexus`. Chart.js lee los colores al crear el gráfico, así que al cambiar de tema en vivo hay que re-renderizar (destruir y recrear).

## Desarrollo local

```bash
python3 scripts/build_hub.py        # regenerar index.html
python3 -m pytest scripts/tests/ -q # tests del generador y del runner
```

## Cron

`.github/workflows/update-data.yml` (cada 4 h UTC): corre los pipelines a-medida existentes, luego auto-discovery de los `query.sql` nuevos, luego regenera el hub, y commitea con el `GITHUB_TOKEN` por defecto. Branch protection + un PAT `HUB_PUSH_TOKEN` quedan como opción futura (no necesarios hoy).

## Más detalle

- Flujo de líder paso a paso: `CONTRIBUTING.md`
- Diseño y plan completos: `docs/superpowers/specs/2026-05-26-hub-multilider-design.md` y `docs/superpowers/plans/2026-05-26-hub-multilider.md`
