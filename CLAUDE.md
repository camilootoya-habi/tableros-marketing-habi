# Growth & Marketing Hub — guía para agentes

Hub de tableros de marketing/growth de Habi. Sitio **estático** en GitHub Pages, **multi-líder**.
Live: https://camilootoya-habi.github.io/tableros-marketing-habi/

## Reglas de oro (no romper)

1. **NUNCA edites el `index.html` de la raíz.** Es un artefacto **GENERADO** por `scripts/build_hub.py`; cualquier cambio a mano se borra en el próximo build. Para cambiar el hub, edita los `meta.json` / `hub.config.json` y corre `python3 scripts/build_hub.py`.
2. **Si eres el agente de un líder de canal: NUNCA pushees a `main`.** Trabaja en una rama y abre un **Pull Request**. Solo Camilo (`@camilootoya-habi`) revisa y mergea. (Hoy no hay branch protection que lo impida — respétalo por convención.)
3. No toques los pipelines a-medida del cron en `.github/workflows/update-data.yml` salvo que sepas exactamente lo que haces.

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

## Dos cosas viven en este repo: tableros y documentos

No es lo mismo y no se tratan igual. Al agregar algo, lo primero es decidir cuál es.

| | **Tablero** | **Documento** |
|---|---|---|
| Qué es | Datos **vivos** conectados a BigQuery | Una **foto**: el análisis de un momento |
| Se refresca | Sí, por workflow. Nadie lo actualiza a mano | **No.** Su número de hoy es el mismo del año que viene |
| Datos de BQ | Siempre | Puede tenerlos, pero **quedan congelados a propósito** |
| `section` | `dashboard` | `analysis` o `reference` |
| Para qué sirve | Seguir un indicador en el tiempo | Dejar constancia de una conclusión y su evidencia |
| Hoy hay | 18 | 8 |

**Por qué un documento NO debe quedar conectado:** su valor es ser citable. Un postmortem
que diga "la campaña cayó 32%" tiene que seguir diciendo 32% cuando alguien lo abra en seis
meses; si estuviera conectado, el número se movería y la conclusión escrita al lado dejaría
de tener sentido. Un documento con datos vivos es un documento que se autodestruye.

Cómo se reconoce en el repo: un tablero tiene `.sql` propios y/o un paso en
`.github/workflows/update-data.yml` que reescribe su `.json`. Un documento no tiene ninguna
de las dos. **Caso intermedio:** `asignados-comercial-mm` y `diagnostico-performance-co`
llevan `.sql` pero **ningún paso en el workflow** — son fotos reproducibles: se puede volver
a correr la query a mano, pero nadie la corre sola. Eso está bien y es deliberado; si algún
día se les agrega al cron, dejan de ser documentos.

Nombres: un documento se rotula como tal en su `title` (p. ej. `Referencias - Marketing
Sellers`), para que en el hub se distinga de un tablero sin tener que abrirlo.

## Contrato de `meta.json`

```json
{ "title": "...", "description": "...", "country": "CO",
  "section": "dashboard", "order": 10, "query": "query.sql",
  "featured": true, "maximum_bytes_billed": 5000000000 }
```
- `section`: `dashboard` | `analysis` | `reference` (sub-grupo dentro del dueño). Ver la tabla de arriba: `dashboard` = tablero, los otros dos = documento.
- `order`: menor = más arriba en su sección. Tableros nuevos → `order` mayor (quedan al final, orden cronológico). `order: 0` se reserva al tablero oficial que debe abrir la sección.
- `featured`: opcional. `true` resalta la card en **verde neón** con badge *oficial*. Solo para la fuente de verdad de un indicador — ver `docs/marketing/tableros-oficiales.md` (el verde se gana; si media hub está resaltada, el resaltado no comunica nada).
- `query` / `maximum_bytes_billed`: opcionales. Sin `query` el cron genérico lo ignora — pero eso **no** significa que sea estático: `marketing-sellers` y `wbr-2-0` se refrescan por pasos dedicados en el workflow. Tope de costo por query: 5 GB por defecto.

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
