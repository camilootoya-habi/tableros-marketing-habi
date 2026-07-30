# Cierres y captaciones del Marketing Loop — diseño

**Fecha:** 2026-07-30 · **Tablero:** `marketing-loop/` · **Rama:** `feat/loop-cierres-captaciones`

## Problema

El tablero mide el loop hasta *asignados* y hasta el funnel comparativo de 14 días. No responde la
pregunta de negocio que sigue: **de los leads que el loop revive, cuántos terminan en una compra
cerrada o en una captación de la inmobiliaria, mes a mes.**

## Definiciones (cerradas con Camilo, 2026-07-30)

Una fila por (mes, país). Se cuentan **leads únicos** (`COUNT(DISTINCT nid)`), fechados por el **mes
en que ocurrió el evento** (`fecha` de la tabla de funnel), no por el mes de creación del lead.

| | Captaciones | Cierres |
|---|---|---|
| **CO** | `sellers-main-prod.bi_co.seguimiento_inmobiliaria_col` · `etapa='Captaciones' AND valor='Captación normal'` | `papyrus-data.habi_wh_bi.funnel_diarios_col` · `TRIM(valor)='Cierre - Comprado'` |
| **MX** | `sellers-main-prod.bi_mx.seguimiento_inmobiliaria_mex_copia` · `valor='Firma'` | `sellers-main-prod.bi_mx.seguimiento_funnel_mex` · `valor='Cierre - Comprado'` |

**Población:** nids con `utm_campaign LIKE '%reinteresados%'` en `sellers-main-prod.hubspot.deals`,
con `country IN ('Colombia','México')`. Es el **mismo predicado que `query_asignados.sql`** — los dos
bloques del tablero tienen que hablar de la misma cohorte o los números no se pueden comparar entre sí.

### Por qué estas definiciones y no otras

- **`etapa` no es una columna común.** Solo `seguimiento_inmobiliaria_col` la usa como nombre del
  hito. En `seguimiento_funnel_mex` existe pero guarda el *dealstage actual con el pipeline entre
  paréntesis* (`"Agendado (Sellers - Market Maker MX (NUEVO))"`), y en las otras dos no existe. El
  evento vive en `valor` en 3 de las 4 tablas.
- **`Cierre OCD` NO se suma.** Es el mismo cierre visto dos veces: de 1.452 nids con cierre en 2026,
  1.380 tienen ambos valores y 1.295 en la misma fecha exacta (promedio 0,1 días de diferencia).
  Sumarlos duplicaría el cierre. Se ignora.
- **MX viene con doble espacio** en algunos valores (`'Cierre  OCD'`), así que el filtro normaliza con
  `REGEXP_REPLACE(TRIM(valor), r'\s+', ' ')`.
- **`_mex_copia` está inflada ~775 filas por nid** (1.507.492 filas para 1.944 nids en `Firma`). El
  `DISTINCT` no es opcional.
- **`Firma` es más laxa que `captaciones_3_checks`** (1.944 vs 734 nids históricos). Con `Firma` la
  cohorte del loop da 18 leads; con `3_checks` da 0. Decisión de Camilo: `Firma`.
- **`Captado para inmobiliaria`** (funnel MM CO, 365 leads del loop) es el *handoff* MM→INMO, no un
  mandato firmado. **Fuera de alcance** en esta sección.

## Baseline al momento del diseño

| Mes | CO captaciones | CO cierres | MX captaciones | MX cierres |
|---|---|---|---|---|
| 2026-06 | 7 | — | 3 | — |
| 2026-07 | 14 | 3 | 15 | 5 |

Los números son bajos **por diseño, no por falta de datos**: la cohorte con UTM del loop arranca el
**17-jun-2026 (MX)** y **22-jun-2026 (CO)**, y un cierre madura en meses. La sección lleva una nota
fija que lo dice, para que nadie lea "3 cierres" como un fracaso del canal.

## Arquitectura

### Cadencia y costo — la restricción que manda el diseño

La query escanea **9,26 GB** y **no baja con filtros de fecha** porque las tablas no están
particionadas por `fecha` (verificado con dry-run: 9,22 GB sin filtro vs 9,26 GB con
`fecha >= '2026-06-01'`). El 71% del escaneo es una sola tabla: `_mex_copia` con 6,55 GB; las otras
cuatro fuentes juntas son 0,18 GB.

En el cron de 10 minutos serían ~1,3 TB/día (~$250/mes). **Por eso la sección NO va en
`build_data.py`.** Decisión: **workflow diario propio que escribe su propio archivo.**

- Nuevo `.github/workflows/update-loop-cierres.yml`, cron 1x/día, escribe `marketing-loop/cierres.json`.
- El tablero lo lee con un `fetch` aparte, **siguiendo el patrón que ya existe** para `audit.json`
  (línea ~420 de `index.html`): `try/catch` que deja la variable en `null` si el archivo no está.
- Costo: ~9,26 GB/día ≈ **$1,7/mes**.
- Beneficio de aislarlo: no toca el cron de 10 minutos (que se acaba de arreglar) y un fallo aquí no
  puede tumbar el resto del tablero.

Se descartó meterlo en `update-data.yml` (~$10/mes y es el cron con el secret roto y fallas
intermitentes sin diagnosticar) y la guarda de frescura dentro del cron de 10 minutos (agrega lógica
de estado, que es justo el patrón que congeló el tablero 2 días sin avisar).

### Contrato de `cierres.json`

```json
{
  "updated": "2026-07-30T09:00Z",
  "rows": [
    {"mes": "2026-06", "pais": "CO", "captaciones": 7,  "cierres": 0},
    {"mes": "2026-07", "pais": "MX", "captaciones": 15, "cierres": 5}
  ]
}
```

Filas planas con campo `pais`, que es la forma que ya usan `comparativa` y `asignados` en este
tablero (`(D.comparativa||[]).filter(x => x.pais === country)`). Un mes sin eventos de un tipo trae
`0`, no se omite la fila: el gráfico necesita el eje completo.

`updated` viaja dentro del archivo para poder mostrar la frescura en la UI. Si `cierres.json` tiene
más de 48 h, la sección lo dice en la nota en vez de fingir que el dato es de hoy.

### UI

En `marketing-loop/index.html`, **justo debajo** del bloque `Funnel comparativo · reinteresados vs
WEB nuevo` (el `<section class="panel"><div id="comparativa"></div></section>` de la línea ~230):

1. `div.tabletitle` con el título y su `button.help-btn` → `openHelp('cc')`.
2. `section.panel > div.ch > canvas` con barras agrupadas por mes vía `mkChart` (estándar del repo,
   Chart.js por CDN): dos series, captaciones y cierres.
3. Tabla mensual debajo (`div.tbl-wrap.ftab`) con mes, captaciones, cierres.
4. `p.note` con la nota de maduración de cohorte y la frescura del archivo.
5. Entrada nueva en el objeto de ayuda (línea ~719) con las definiciones por país, nombrando las
   tablas y aclarando que `Cierre OCD` se excluye a propósito.

Respeta el selector `input[name=pais]` existente: al cambiar de país se re-renderiza filtrando por
`pais`. Chart.js lee los colores al crear el gráfico, así que el cambio de tema exige destruir y
recrear (ya resuelto por `mkChart` y el registro `_charts` del template).

### Degradación

| Situación | Comportamiento |
|---|---|
| `cierres.json` no existe (primer deploy) | La sección no se dibuja. Sin error en consola, sin hueco visual. |
| El archivo existe pero `rows` está vacío | Se dibuja el título y la nota explicando que aún no hay eventos. **No** un gráfico en cero. |
| El archivo tiene > 48 h | Se dibuja normal + aviso de desactualización en la nota. |
| La query falla en el cron | El workflow **falla ruidosamente** (exit ≠ 0). No se traga el error: es exactamente el bug que dejó el tablero congelado 2 días. |

## Pruebas

- `query_cierres_captaciones.sql` reproduce el baseline de arriba (39 captaciones y 8 cierres al 2026-07-30).
- El total por país cuadra contra un conteo directo de cada tabla por separado (sin el join a la cohorte).
- Ningún mes con filas duplicadas: `COUNT(*) = COUNT(DISTINCT (mes,pais))` en el JSON.
- El script de build escribe `cierres.json` con `updated` y falla con exit ≠ 0 si BQ devuelve error.
- Revisión en `localhost:8091` antes de cualquier push.

## Fuera de alcance

- `Captado para inmobiliaria` (handoff MM→INMO) y `Referido para inmobiliaria`.
- `Cierre OCD` como métrica separada.
- Cohortes por mes de creación / curvas de maduración.
- MX `captaciones_3_checks` como definición alterna.
- Atribución por la tabla `recreation` de Neon en vez de la UTM de HubSpot.

## Riesgos

- **`_mex_copia`**: el nombre y la inflación de filas sugieren una tabla de trabajo, no un mart
  estable. Si desaparece o cambia, MX se queda sin captaciones. Mitigación: la degradación de arriba
  y el workflow que falla ruidosamente.
- **Migración pendiente**: existe la rama `feat/migrate-marketing-loop-out` (spec para mover este
  tablero a su propio repo). Si esa migración avanza, esta sección se muda con él.
