# Hub multi-líder — Diseño

- **Fecha:** 2026-05-26
- **Estado:** Aprobado (pendiente plan de implementación)
- **Repo:** `camilootoya-habi/tableros-marketing-habi`
- **Autor/owner:** Camilo Otoya (con Jean-Claude)

## Contexto

El Growth & Marketing Hub hoy es un solo `index.html` organizado por **tipo**
(Analysis / Dashboards / Reference), mantenido únicamente por Camilo. Queremos
que **Camilo + 4 líderes de canal** trabajen sobre el mismo hub:

- La sección de Camilo (arriba) es **marketing general**.
- Cada líder tiene sus propios tableros, análisis y documentación de **su canal**.
- Un líder debe poder montar su tablero y que **su query quede enchufado al cron**
  para que se mantenga actualizado solo.

Primer líder en el flujo: **Sebastián Ciendua — Performance Colombia** (ya tiene
permiso `write` en el repo).

## Objetivos

1. Cambiar el eje de organización del hub de **tipo** a **dueño/canal**, sin perder
   el sub-agrupamiento por tipo dentro de cada dueño.
2. Permitir que 5 personas contribuyan sin pisarse ni romper el cron compartido.
3. Que agregar un tablero nuevo (de cualquier líder) tenga **costo marginal mínimo**:
   crear una carpeta, sin editar archivos compartidos a mano.
4. Conectar el query de cada tablero nuevo al cron consolidado de forma automática.

## No-objetivos (YAGNI)

- **No** migrar los pipelines de datos a-medida existentes (OKR con Sheets, funnel
  con 2 SQL + python, `desempeno-hoy`). Se quedan tal cual; el auto-discovery es
  **aditivo**.
- **No** crear un repo por líder (rompería el cron único; ya descartado).
- **No** construir autenticación per-usuario para el cron. El cron sigue corriendo
  con las credenciales de Camilo; los líderes desarrollan su SQL con **sus propios
  accesos a BigQuery** (confirmado que los tienen).
- **No** cambiar las URLs de los tableros actuales de Camilo (se quedan en la raíz).

## Decisiones (tomadas en brainstorming)

| # | Decisión | Elegido |
|---|----------|---------|
| 1 | Arquitectura | Monorepo único (el actual) |
| 2 | Layout de líderes en el hub | Secciones **inline** por líder, una sola página |
| 3 | Conexión query → cron | **Auto-discovery** por convención |
| 4 | Gobernanza | **PR + revisión** (branch protection + CODEOWNERS) |
| 5 | Construcción del `index.html` | **Generado** desde `meta.json` (no editar a mano) |

## Arquitectura

### Estructura de carpetas

```
tableros-marketing-habi/
├── index.html                  ← GENERADO por build_hub.py — NO editar a mano
├── hub.config.json             ← orden de secciones, header, cards externas
├── scripts/
│   ├── build_hub.py            ← regenera index.html desde meta.json + hub.config.json
│   ├── run_queries.py          ← auto-discovery: corre los query.sql nuevos
│   └── daily-pull.sh           ← (existente)
├── .github/
│   ├── workflows/
│   │   ├── update-data.yml     ← cron (existente + paso de auto-discovery + build hub)
│   │   └── desempeno-hoy.yml   ← (existente, sin cambios)
│   └── CODEOWNERS              ← protege archivos compartidos
│
├── <tablero-general>/          ← tableros de Camilo (raíz, URLs intactas)
│   ├── index.html
│   ├── meta.json
│   ├── query.sql               ← opcional
│   └── data.json               ← generado (si hay query)
│   …
│
└── canales/
    └── sebastian-ciendua/
        ├── _leader.json        ← { name, channel, order }
        └── <su-tablero>/
            ├── index.html
            ├── meta.json
            ├── query.sql
            └── data.json
```

**Inferencia de dueño por ubicación:**
- Carpeta de tablero en la **raíz** → dueño = `general` (Camilo).
- Carpeta bajo `canales/<lider>/` → dueño = ese líder.

Los tableros generales existentes (raíz, no se mueven):
`asignados-creacion`, `calificados-mm-inmo`, `creativo-pamela`, `desempeno-hoy`,
`docs-marketing` (reference), `funnel-fuentes`, `funnel-web-mx`,
`incompletos-colombia`, `incompletos-direccion`, `marketing-wbr`, `okr-marketing`,
`pmax-mexico-quality`, `prioridad-mm`, `tablero-marketing`, `wbr-2-0`.

Los 2 informes satélite (`analisis-asignados-co`, `analisis-mty-multimedios`) siguen
siendo **repos aparte**; se enlazan desde `hub.config.json` como cards externas en
la sección General → Analysis.

## El contrato de cada tablero — `meta.json`

Toda carpeta de tablero (general o de líder) lleva un `meta.json`:

```json
{
  "title": "Leads Incompletos",
  "description": "Análisis de leads que quedan en estado incompleto…",
  "country": "CO",
  "section": "dashboard",
  "order": 10,
  "query": "query.sql",
  "data": "data.json",
  "maximum_bytes_billed": 5000000000
}
```

| Campo | Req | Descripción |
|-------|-----|-------------|
| `title` | sí | Título de la card |
| `description` | sí | Texto de la card |
| `country` | sí | `CO`, `MX`, `CO & MX`… (se renderiza como chip) |
| `section` | sí | `dashboard` \| `analysis` \| `reference` (sub-grupo dentro del dueño) |
| `order` | no | Orden dentro de su sub-grupo (default: alfabético por título) |
| `query` | no | Nombre del archivo SQL. Si está, el cron lo corre. Si no, tablero estático |
| `data` | no | Archivo de salida del query (default `data.json`) |
| `maximum_bytes_billed` | no | Tope de costo en BQ (default global definido en el runner) |

- Con `query` → el cron lo ejecuta bajo las creds de Camilo (con tope de bytes) y
  escribe `data`.
- Sin `query` → estático: el cron lo ignora, pero igual se renderiza la card.

### Registro de un líder — `canales/<lider>/_leader.json`

```json
{ "name": "Sebastián Ciendua", "channel": "Performance Colombia", "order": 1 }
```

Lo crea Camilo (es config compartida que define el orden de las secciones).

### Config global — `hub.config.json`

```json
{
  "title": "Growth & Marketing",
  "subtitle": "Lo que no se mide no se mejora…",
  "general": { "title": "General · Marketing", "order": 0 },
  "external_cards": [
    {
      "section": "analysis",
      "title": "Análisis de asignados — 2026",
      "description": "Postmortem de la caída de asignados…",
      "country": "CO",
      "url": "https://camilootoya-habi.github.io/analisis-asignados-co/"
    },
    {
      "section": "analysis",
      "title": "Postmortem campaña Multimedios — MTY",
      "description": "Impacto de la campaña ALL-IN TUHABI…",
      "country": "MX",
      "url": "https://camilootoya-habi.github.io/analisis-mty-multimedios/"
    }
  ]
}
```

## El cron — auto-discovery aditivo

Los pasos actuales de `update-data.yml` (pipelines a-medida) **no se tocan**. Se
**agregan** dos pasos al final:

1. **`run_queries.py`** (auto-discovery):
   - Escanea todos los `meta.json` que tengan campo `query`.
   - ⚠️ **Los tableros generales existentes NO declaran `query`** en su `meta.json`
     (sus datos los siguen produciendo los pasos a-medida actuales). Así el
     auto-discovery solo corre tableros **nuevos** y evita la doble ejecución.
   - Para cada uno corre el SQL con:
     - `maximum_bytes_billed` del meta (o el default global) → guardrail de costo.
     - timeout por query.
     - aislamiento de fallos: si un query falla, se loguea y se sigue con los demás
       (patrón `continue-on-error` / `if: always()`).
   - Escribe el resultado en el `data` adyacente.
   - **Escape hatch:** si una carpeta tiene `build.py`, se ejecuta ese script en vez
     del camino `query.sql` (para casos complejos de un líder).
2. **`build_hub.py`** → regenera `index.html`.
3. Commit de los `data.json` cambiados + `index.html`.

Schedule sin cambios: `0 */4 * * *` (cada 4 h UTC).

**Guardrail de costo por defecto:** definir un `DEFAULT_MAX_BYTES` razonable en
`run_queries.py` (p. ej. 5 GB) para que ningún query nuevo dispare costo de BQ sin
querer; un líder puede subirlo explícitamente en su `meta.json` si lo justifica (y
se ve en el PR).

## El generador del hub — `build_hub.py`

- **Descubrimiento:** un "tablero" es cualquier carpeta que contenga un `meta.json`.
  Carpetas sin `meta.json` (`scripts/`, `docs/`, `.github/`) se ignoran.
- **Entradas:** `hub.config.json` + todos los `meta.json` (raíz y `canales/**`) +
  los `_leader.json`.
- **Lógica:**
  1. Sección **General** primero (orden `hub.config.general.order`), con sub-grupos
     `Analysis / Dashboards / Reference` (incluye las `external_cards`).
  2. Luego una **sección inline por líder**, ordenadas por `_leader.json.order`,
     cada una titulada `"<name> · <channel>"`, con sus propios sub-grupos por `section`.
  3. Dentro de cada sub-grupo, cards ordenadas por `order` (luego por título).
- **Salida:** `index.html` con el **mismo tema visual actual** (se reusa el CSS y el
  toggle de tema que ya viven en `index.html`; se extrae a plantilla).
- **Links:** internos → ruta relativa de la carpeta; externos → `url` del meta/config.
- Lo corre el CI en cada merge a `main` (y el cron). El `index.html` queda como
  artefacto generado; editarlo a mano se revierte en el siguiente build.

## Gobernanza — PR + revisión

- **Branch protection** en `main` (disponible gratis en repos públicos):
  - PR obligatorio antes de merge, sin push directo a `main`.
  - Requerir 1 aprobación.
  - Requerir review de code owners.
- **CODEOWNERS:** los archivos compartidos requieren review de `@camilootoya-habi`:
  ```
  /index.html            @camilootoya-habi
  /hub.config.json       @camilootoya-habi
  /scripts/              @camilootoya-habi
  /.github/              @camilootoya-habi
  ```
  Las carpetas de líder (`/canales/<lider>/`) pueden tener al líder como owner para
  que revise su propia área.
- ⚠️ **Gotcha del auto-commit:** el cron pushea `data.json` + `index.html` a `main`.
  Con branch protection activa hay que **permitir el bypass** para ese commit
  automatizado (excepción al actor del workflow, o usar un token/deploy key con
  permiso de bypass). Si no se configura, el cron queda bloqueado.

## Flujo repetible para un líder — `CONTRIBUTING.md`

1. `git pull` y `git checkout -b sebastian/<tablero>`.
2. Copiar la **plantilla** a `canales/sebastian-ciendua/<tablero>/`.
3. Llenar `index.html`, `meta.json` y `query.sql`; probar el query en BigQuery con
   sus propias credenciales.
4. `git push` y abrir un **PR**.
5. Camilo revisa (costo y correctitud del query, contenido) y **mergea**.
6. El CI corre el query → `data.json`, regenera el hub → la card del líder aparece y
   el tablero queda **auto-actualizándose a diario**.

Se entrega una **plantilla de tablero** (`scripts/template/`) con `index.html`
mínimo que hace `fetch('data.json')`, un `meta.json` de ejemplo y un `query.sql`
comentado, siguiendo el tema visual y el favicon 📢 estándar.

## Backfill (parte de la implementación)

- Crear `meta.json` para los 15 tableros existentes de la raíz (extrayendo
  título/descripción/país/section del `index.html` actual). **Sin campo `query`**
  (sus datos los siguen generando los pasos a-medida del cron).
- Mover las 2 cards externas a `hub.config.json`.
- Generar el primer `index.html` con `build_hub.py` y verificar **paridad visual y
  de links** con el hub actual (mismo contenido, mismas URLs).

## Piloto: Sebastián Ciendua — Performance Colombia

- Crear `canales/sebastian-ciendua/_leader.json`
  (`{ "name": "Sebastián Ciendua", "channel": "Performance Colombia", "order": 1 }`).
- Entregarle la plantilla + `CONTRIBUTING.md`.
- Él monta su primer tablero como prueba end-to-end del flujo (PR → review → merge →
  cron → card viva).

## Dependencias y riesgos

- ✅ Los líderes tienen acceso propio a BigQuery (confirmado) → pueden iterar su SQL.
- ⚠️ El cron corre con las creds de Camilo: un query nuevo costoso corre a diario.
  Mitigación: `maximum_bytes_billed` por defecto + revisión del query en el PR.
- ⚠️ Branch protection + auto-commit del cron: configurar el bypass (ver gotcha).
- El `index.html` pasa a ser generado: hay que comunicar que **no se edita a mano**
  (un editor desprevenido perdería su cambio en el siguiente build).

## Fases de implementación (alto nivel; el detalle va en el plan)

1. **Convención + generador:** `meta.json` schema, `build_hub.py`, plantilla de hub,
   backfill de los 15 + `hub.config.json`; verificar paridad con el hub actual.
2. **Cron aditivo:** `run_queries.py` con guardrails + escape hatch; engancharlo a
   `update-data.yml` + paso de `build_hub.py`.
3. **Gobernanza:** branch protection, CODEOWNERS, bypass del auto-commit,
   `CONTRIBUTING.md`.
4. **Piloto Sebastián:** `_leader.json` + acompañar su primer tablero por el flujo.
```
