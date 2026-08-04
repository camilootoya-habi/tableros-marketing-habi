# Tablero — Seguimiento de asignación MM vs INMO (Colombia)

**Fecha:** 2026-08-04 · **País:** CO (MX es fase 2) · **Destino:** `asignacion-co/` en la raíz del hub (tablero general)

## Problema

Hoy no sabemos, de los leads que se asignan en Colombia, cuántos van a Market Maker y cuántos a Inmobiliaria, ni cuántos de los que terminan en INMO pasaron primero por MM. Tampoco sabemos si el indicador de asignados del WBR mart coincide con un "ever asignado" construido desde las tablas de asignación.

Un query previo de un compañero apuntaba a esto pero se quedaba corto: su universo era solo `etapa='Asignado'` de la tabla INMO, así que no tenía a MM como destino — le faltaba la mitad del numerador y todo el denominador conjunto.

## Preguntas que el tablero debe responder

1. Por cosecha de creación: de los leads creados, ¿cuántos se asignaron alguna vez, y a qué producto llegaron primero?
2. De los que llegan a INMO en un período: ¿qué proporción llegó directo, cuántos después de MM, y cuántos pasaron por GABI antes?
3. Lo mismo para MM.
4. ¿Por qué el "ever asignado" no coincide con los asignados del WBR mart, y qué parte de esa diferencia es arreglable?

## Decisiones tomadas

| Decisión | Elección |
|---|---|
| **Universo** | Todos los asignados, sin filtro de fuente. El WBR mart entra solo como comparación. |
| **Señal de "ever asignado"** | Unión de señales fechadas (ver Corrección abajo). |
| **Desasignados** | Fuera de la v1. |
| **Maduración** | Ventana fija por capa + marca visual de cosecha inmadura. |
| **Arquitectura de datos** | Un `query.sql` que agrega desde un CTE `base` a nivel nid, escrito para poder materializarse después. |
| **Layout** | Tres lentes apiladas, sin selector de lente. Granularidad y filtros globales arriba. |

## ⚠️ Corrección de diseño: la fecha de GABI

La primera versión de este diseño usaba `product_qualified` como una de las tres señales fechadas de primera asignación. **Es inviable:** `product_qualified` es una columna suelta en `habi_db_tabla_negocio_inmueble`, **sin timestamp**, y **no aparece en `hubspot.historical`** (cero registros verificados 2026-08-04). Es un valor actual, no una serie.

Consecuencias:

- Las señales fechadas son **dos**: `bi_co.seguimiento_asignacion_ibuyer_co` (que ya distingue `tipo` = gabi/comercial, y ahí GABI **sí** queda fechado) y `hubspot.historical` con `propiedad='hubspot_owner_id'`.
- `product_qualified` se usa como **atributo** (la elección de producto de GABI), no como señal de fecha. Valores en CO para leads creados desde 2026-05-01: `transient` 43.291 · `ibuyer_and_real_estate` 14.257 · `real_estate` 4.861 · `ibuyer` 2.963 · nulo 62.837.
- "Escogió MM en GABI" se lee como `product_qualified IN ('ibuyer','ibuyer_and_real_estate')`. **No se puede afirmar que la calificación fue anterior al paso a MM, ni si cambió en el camino.** Cualquier lectura de esa ruta debe rotularse como estado final.
- `transient` es el valor más frecuente y no es ni MM ni INMO: se muestra como categoría propia, no se reparte.
- **Propuesta de mejora derivada:** instrumentar `product_qualified` en el historial de HubSpot. Sin eso, la secuencia GABI→producto no es fechable.

## Fuentes de datos

| Rol | Tabla | Notas |
|---|---|---|
| Universo de leads + cosecha | `papyrus-data.habi_wh_bi.tabla_inmuebles_general` | ⚠️ `papyrus-data` no permite crear jobs: facturar en `sellers-main-prod` con path completo. |
| Asignaciones (ambos productos) | `sellers-main-prod.bi_co.seguimiento_asignacion_ibuyer_co` | `tipo_asignacion` (Primer Asignación/Regestión), `tipo` (gabi/comercial). ⚠️ Su columna `pipeline` es **snapshot** — 369.200 nids con exactamente 1 pipeline, ninguno con 2. **No usar para la secuencia.** |
| Secuencia de productos + owner | `sellers-main-prod.hubspot.historical` | `propiedad='pipeline'` y `'hubspot_owner_id'`. Particionada por MONTH en `fecha`, clusterizada por `propiedad`. `valor` es STRING. ⚠️ ~5 h de rezago (batch). |
| Catálogo de pipelines | `sellers-main-prod.hubspot.deal_pipelines_stages` / `deal_pipelines` | MM = `798578615` · INMO = `803674753` · legacy = `1679217`. ⚠️ Los labels de MM CO e INMO CO son casi idénticos; los IDs de stage sí son únicos por pipeline. |
| Elección de GABI | `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble.product_qualified` | Snapshot sin fecha (ver Corrección). |
| Comparación WBR | `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` | LEFT JOIN por nid + `pais='colombia'`. |
| Origen de asignación INMO (opcional) | `sellers-main-prod.bi_co.tablero_asignacion_inmo_col` | Ya trae `origen_asignacion` (ASIGNADO_WORKFLOW 39.121 / ENTRADA_DIRECTA 4.533) y `etapa_entrada`. ⚠️ Su `estado` es la tipificación del buy box, no el estado del negocio. |

**Costo:** dry-run del CTE de `historical` acotado por fecha y propiedades = **2,03 GB**. `maximum_bytes_billed` en el `meta.json`: 5 GB (default del hub). Si al integrar todo se pasa, partir en dos queries.

## El CTE `base` (una fila por nid)

Escrito para poder convertirse en `CREATE TABLE bi_co.base_asignacion_co AS …` sin reescribir nada.

| Campo | Definición |
|---|---|
| `nid`, `fecha_creacion`, `fuente_id`, `fuente`, `area_metropolitana` | del universo de leads |
| `f_asig_seguimiento`, `tipo_asignacion_1`, `tipo_1` | primera fila por nid en `seguimiento_asignacion_ibuyer_co`, con `ARRAY_AGG(… ORDER BY fecha_asignacion LIMIT 1)` — **nunca `ANY_VALUE`** |
| `f_owner` | primer `hubspot_owner_id` no vacío en `historical` |
| `f_primera_asignacion` | `LEAST(f_asig_seguimiento, f_owner)` |
| `senal_primera` | cuál de las dos llegó primero → diagnóstico de cobertura de cada señal |
| `gabi_flag` | `tipo_1 = 'gabi'` |
| `gabi_producto` | `product_qualified` (atributo, sin fecha) |
| `pipeline_1`, `f_pipeline_1` | primer valor de `propiedad='pipeline'` ∈ {MM, INMO, LEGACY} |
| `pipeline_2`, `f_pipeline_2` | primer valor **distinto** de `pipeline_1` |
| `f_pipeline_mm`, `f_pipeline_inmo` | primera entrada a cada producto (anclas de las lentes B y C) |
| `ruta` | taxonomía derivada (ver lentes B/C) |
| `en_wbr_mart` | flag del LEFT JOIN contra el mart |

**Ventana:** cosechas desde **2026-01-01**. La serie se dibuja completa con un **corte visual marcado en abril 2026** ("cambio de lógica de asignación") y zoom por defecto en los últimos 6 meses. Los asignados MM caen de 39,6k (sep-2025) a ~8k (jun/jul-2026): el quiebre se muestra, no se trunca.

## Capas y ventanas de maduración

| Capa | Métrica | Denominador | Ventana |
|---|---|---|---|
| L1 | ever asignado | leads creados | ≤ 30 d |
| L2 | GABI vs directo a pipeline | asignados L1 | ≤ 30 d |
| L3 | primer producto: MM / INMO / legacy | asignados L1 | ≤ 30 d |
| L4 | segunda asignación: mismo producto / cruce / sin segunda | asignados L1 | ≤ 90 d |

**Dónde aparece cada capa:** L1-L3 son las columnas de la lente A. L4 no es una columna de A — es lo que alimenta las **rutas** de las lentes B y C (el `pipeline_2` del CTE). Se define aquí como capa porque comparte la lógica de maduración.

**"Ever" vs ventana fija:** la columna Ever asignado de la lente A se mide **dentro de 30 d** para que las cosechas sean comparables entre sí. El "ever" literal (sin límite) va como columna de referencia al lado, y la diferencia entre ambas es en sí misma una señal de cuánto tarda la asignación en esa cosecha.

L2 y L3 derivan del **mismo evento** (la primera asignación), así que comparten ventana y no son secuenciales entre sí. Una cosecha puede estar madura en L1 e inmadura en L4: la marca de inmadurez es **por capa**, no por fila. Justificación de los 90 d en L4: MM→INMO tiene mediana 10 d y **p90 52 d** (medido abr-jul 2026).

## Layout

```
Granularidad: [Semana] [Mes] [Ciclo mié-mar]     ← global
Filtro: fuente · área metropolitana · equipo      ← selector estándar, uno a la vez
─── A · Cosechas por fecha de creación
─── B · Llegadas a INMO — desde dónde vienen
─── C · Llegadas a MM — desde dónde vienen
─── Conclusiones · reconciliación con el WBR mart
```

Sin selector de lente: las tres apiladas, últimos 20 períodos cada una.

**⚠️ Requisito de diseño no negociable:** A ancla en **fecha de creación**, B y C anclan en **fecha de llegada al producto**. El mismo período en las tres tablas **no** habla del mismo grupo de leads. Cada bloque lleva su denominador escrito en el subtítulo, con peso tipográfico — no como nota al pie. Leídas en vertical, el riesgo de sumarlas mentalmente es alto.

### Lente A — Cosechas (ancla: `fecha_creacion`)

| Cosecha | Creados | Asignado ≤30d | Ever asignado (ref.) | GABI | Directo a pipeline | 1er producto MM | INMO | legacy |

`count (%)` inline, heatmap en el %, cosechas inmaduras atenuadas con label "inmadura". El % siempre sobre **asignados**, no sobre creados (salvo la columna Ever asignado). Debajo: gráfica de líneas con % ever-asignado y mix MM/INMO.

### Lente B — Llegadas a INMO (ancla: `f_pipeline_inmo`)

Denominador = leads que llegaron a INMO en el período (mezcla cosechas de creación, por diseño).

| Período | Llegadas INMO | Directo | GABI → INMO | GABI(MM) → MM → INMO | MM → INMO | INMO → MM → INMO |

Panel de **tiempos por salto**: creación → GABI, GABI → MM, MM → INMO. **Mediana y p90, nunca promedio** (la distribución tiene cola larga). Corte adicional por `gabi_producto` con la advertencia de estado final.

Baseline medido (abr-jul 2026, vía `propiedad='pipeline'`): MM→INMO **8.459** nids (mediana 10 d, p90 52 d) · solo INMO 15.958 · solo MM 13.922 · INMO→MM 373. Es decir ~35% de las llegadas a INMO pasaron por MM.

### Lente C — Llegadas a MM (ancla: `f_pipeline_mm`)

Rutas espejo: Directo · GABI → MM · GABI(INMO) → INMO → MM · INMO → MM · re-entrada a MM.

**Expectativa a validar, no supuesto:** MM es la entrada por defecto, así que "Directo" probablemente domine y lo informativo sea el cruce inverso (los 373). Si la lente C resulta trivial, se anota como hallazgo en vez de inflar el tablero.

### Conclusiones — reconciliación con el WBR mart

**Premisa a corregir explícitamente en el texto del tablero:** ever-asignado y el WBR mart **no pueden dar igual por construcción**. El mart es un indicador de *marketing* con 16 filtros (solo WEB, Leadform, Habímetro, Broker, comercial, CRM; excluye Ventanas; aplica reglas de calificación). El ever-asignado cuenta todo lo que se asignó.

Hay que separar dos brechas:
- **Esperada** — universo distinto. No se arregla: se explica y se cuantifica.
- **No esperada** — leads de fuente de marketing, asignados, ausentes del mart (o al revés). **Esto es lo accionable.**

Comparación **a nivel nid** con el flag `en_wbr_mart` sobre la misma cosecha de creación, para no chocar anclajes (el mart cuenta por día de asignación):

| | En el mart | No en el mart |
|---|---|---|
| **Ever asignado** | ✅ coinciden | ⚠️ hallazgo |
| **No asignado** | ⚠️ hallazgo | ✅ coinciden |

Los cuadrantes ⚠️ se descomponen por: fuente no-marketing · Ventanas · filtros de calificación del mart · **resto sin explicar**. El objetivo del análisis es llevar "resto sin explicar" a cero; lo que quede es la propuesta de mejora. Si el informe no separa las dos brechas, cualquier conclusión suena a que el mart está roto cuando no lo está.

## Entregables

1. `asignacion-co/meta.json` — `section: dashboard`, `country: CO`, `order` al final de su sección, `query: query.sql`, `maximum_bytes_billed`.
2. `asignacion-co/query.sql` — CTE `base` a nivel nid + agregaciones de las tres lentes en formato largo.
3. `asignacion-co/index.html` — desde `scripts/templates/dashboard.html`; gráficas con el helper `mkChart` (Chart.js), nunca SVG a mano.
4. Bloque de Conclusiones con el gap descompuesto y la propuesta de mejora.
5. Este spec, commiteado.

**Formato del `data.json`:** una fila por `(lente, granularidad, período, métrica, dimensión, valor_dimensión, conteo)`. Cortes **no cruzados** (uno a la vez) para acotar el tamaño.

## Fuera de alcance (v1)

- México (sus tablas de asignación son otras: `leads_asignados_mm_mx`, `leads_asignados_imobiliaria`, `InmoMX.entrada_asignador`).
- Descartes y sus razones (`razon_de_descarte_mm` / `_inmo`: 41k eventos en jun-jul, taxonomía ya poblada — es la fase 2 más obvia).
- Reasignaciones owner→owner (~90k cambios en 2 meses) y desasignación literal (73 casos: residual, solo serviría como chequeo de anomalía).
- Materializar `bi_co.base_asignacion_co` en BQ (requiere permisos de escritura; el `query.sql` queda listo para ello).
- **Pregunta abierta:** posible fusión con el tablero *Asignados-creación Mart vs Ever*, que ya reconcilia el **conteo**; este reconcilia la **mecánica**. Decidir cuando se vean los dos juntos.

## Riesgos

| Riesgo | Manejo |
|---|---|
| `historical` con ~5 h de rezago | El tablero no es casi-en-vivo. Declararlo en el encabezado. |
| Costo de query | Dry-run medido: 2,03 GB. Tope 5 GB. Si crece, partir en dos queries. |
| Leer los tres bloques como el mismo universo | Denominador en el subtítulo de cada bloque, con peso tipográfico. |
| Cosechas recientes leídas como caída real | Marca de inmadurez por capa + corte visual en abr-2026. |
| Ruta GABI(MM)→MM→INMO sobreinterpretada | Rotular como estado final, no secuencia fechada. |
