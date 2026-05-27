# Tablero "Asignados — Explorador de Filtros" · Diseño

**Autor:** Camilo Otoya (camilootoya@habi.co)
**Fecha:** 2026-05-11
**Estado:** Aprobado por usuario, listo para plan de implementación
**País:** Colombia (MX fuera de alcance v1)

## Contexto y propósito

La tabla `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` es la fuente oficial de "leads asignados Marketing CO". Aplica 16 filtros agrupados en 7 categorías sobre dos capas previas (ver doc Data&BI). Marketing está en proceso de revisar y aprobar/rechazar cada filtro, y un cruce contra el universo esperado de `product_qualified IN ('ibuyer','ibuyer_and_real_estate')` mostró 1.097 nids esperados que no llegan al mart en abril 2026.

Este tablero permite **explorar el impacto cuantitativo de cada filtro** activándolo o desactivándolo en tiempo real, comparando contra la línea base oficial del mart. Sirve dos usos:

1. **Análisis** — apoyar la conversación con Marketing sobre qué filtros mantener
2. **Operativo** — quedarse vivo en el repo con auto-update diario para monitoreo continuo

## Decisiones cerradas en brainstorming

- **Selector de filtros:** checkboxes individuales por filtro (no por grupo, no escenarios)
- **F1 y F2 fijos on (no toggleables):** F1 define el universo base (sin cambio de `hubspot_owner_id` no hay nada que contar); F2 fija la convención "primera asignación cronológica por nid". Toggleables solo F3–F15 (14 filtros).
- **F16 fijo on:** la conversión UTC→Colombia es transversal, no es opcional.
- **Calificado:** event-based, primera entrada a `state_id IN (20, 63)` en `historico_estado_v2` (misma definición que WBR y WBR 2.0). NO se usa el `estado` del deal en HubSpot.
- **Ventana temporal:** **18 períodos** según granularidad seleccionada (18 días / 18 semanas / 18 meses). Default: semana. Data subyacente: 18 meses para soportar el peor caso.
- **Enfoque de datos:** Pre-agregado con **bitmask de 14 bits** (uno por filtro toggleable). Permite cualquier combinación AND de filtros sin recargar.
- **Descomposiciones:**
  - Calificado vs no calificado → bloque de charts/tabla separado del chart principal
  - "Comercial vs no comercial" → NO se incluye como categoría fija; en su lugar los toggles F3, F4, F5 individuales muestran qué incluye cada filtro
- **Comparación contra mart oficial:** línea ámbar dashed siempre visible como referencia
- **Tabla de breakdowns:** efecto **marginal desde la posición actual** del usuario (cuánto más quitaría activar cada filtro hoy apagado)

## Arquitectura

Sub-tablero `asignados-filtros/` dentro del repo `tableros-marketing-habi`, siguiendo el patrón estándar del repo:

```
asignados-filtros/
├── index.html         ← UI vanilla (mismo tema oscuro)
├── data.json          ← auto-update diario
├── query.sql          ← BQ: asignaciones con flags por filtro
└── build_data.py      ← agrega resultado BQ a JSON pre-agregado con bitmask
```

- Auto-update: nuevo step en `.github/workflows/update-data.yml`, cron 13:00 UTC.
- Card en el landing `index.html` del root.
- Live URL: `https://camilootoya-habi.github.io/tableros-marketing-habi/asignados-filtros/`.
- Tema visual compartido: background `#0f172a`, cards `#1e293b`, acento `#818cf8` (universo del usuario), referencia ámbar `#fbbf24` (mart oficial).
- Favicon megáfono estándar.
- Back link al inicio del body.

## Modelo de datos

### Query SQL (`query.sql`)

Replica la lógica del mart desde tablas crudas. Produce **1 fila por asignación válida en universo base** (F1+F2 aplicados como filtros estructurales) con 14 columnas booleanas `pasa_f3`…`pasa_f15` (true = el filtro NO la excluye).

**Universo base:**
- Tabla `papyrus-master.src_sellers_hubspot.history`
- `WHERE propiedad = "hubspot_owner_id"` (F1)
- `QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY fecha ASC) = 1` (F2)
- `WHERE DATE(DATE_SUB(fecha, INTERVAL 5 HOUR)) >= CURRENT_DATE - 540` (F16 + ventana 18 meses)

**Columnas producidas por asignación:**

| Columna | Origen | Notas |
|---|---|---|
| `nid` | `history.nid` | clave |
| `fecha_asignacion` | `DATE_SUB(history.fecha, INTERVAL 5 HOUR)` | F16 aplicado |
| `owner_email` | `IFNULL(sc.email, h.valor)` vía `sc_users_hubspot` | para tooltip futuro |
| `fuente_label` | mapeado desde `tig.fuente_id` | etiqueta del reporte |
| `calificado` | `bool` event-based en `historico_estado_v2` | true si nid llegó a state_id IN (20,63) en cualquier momento |
| `pasa_f3` | `owner_email LIKE "%habi.%"` | |
| `pasa_f4` | `owner_email NOT LIKE "%agente%"` AND `"%delta%"` AND `"%call%"` | |
| `pasa_f5` | `owner_email NOT IN ('alejandroaguirre@habi.co','erickcastillo@tuhabi.mx','victorialechtig@tuhabi.mx')` | |
| `pasa_f6` | regla compuesta: si owner ∈ {lauracruz,alejandrobravo,juanquinones,juanarcos}@habi.co, requiere `deal.contacto_digital IS NOT NULL`; else true | |
| `pasa_f7` | `LOWER(TRIM(deal.estado)) = 'sin pricing incial'` | match exacto del estado del deal |
| `pasa_f8` | `LOWER(TRIM(deal.estado)) = 'no gestionado'` | match exacto |
| `pasa_f9` | `LOWER(TRIM(deal.estado)) = 'cierre'` | match exacto |
| `pasa_f10` | `LOWER(TRIM(deal.estado)) = 'no hay suficientes datos para comparar'` | match exacto |
| `pasa_f11` | `LOWER(tig.calificacion_del_lead_v2) NOT IN ('n','nh')` | |
| `pasa_f12` | `tig.check_a_pricing = 1` | |
| `pasa_f13` | `tig.fecha_creacion IS NOT NULL` | |
| `pasa_f14` | `tig.nid IS NOT NULL` | redundante con join, pero se expone para que el toggle sea coherente con el doc |
| `pasa_f15` | `1` (dummy en v1) | La columna `asignacion_descartes_top` no existe en `tabla_inmuebles_general` con los accesos disponibles. El toggle se mantiene visible pero el flag siempre vale 1 (no excluye nada). Por aclarar con Data&BI cuál es la columna real. |

**Nota importante sobre F7–F10 (semántica OR dentro del grupo Estado):** en el mart oficial estos cuatro flags están combinados como un `IN (...)` único sobre `estado` — esto es OR dentro del grupo, no AND. En el tablero los exponemos por separado para que cada checkbox represente un estado individual. Para cada asignación, **a lo sumo uno** de `pasa_f7..pasa_f10` será true (corresponde al estado real del deal); los otros 3 serán false. Si el estado del deal no es ninguno de los 4 permitidos, los 4 flags serán false.

La consecuencia es que el grupo Estado necesita lógica OR en el frontend, distinta del AND de los otros grupos. Detalles en la sección "Lógica frontend".

### Tablas fuente (v1 implementado, refactorizado por IAM)

Las tablas originalmente planeadas (`papyrus-master.src_sellers_hubspot.history` y `papyrus-staging.src_sellers_hubspot.deal`) no son accesibles desde el workflow. Se refactorizó para usar solo:

- `papyrus-data.habi_wh_bi.tabla_inmuebles_general` — universo base (`fecha_primer_asignacion IS NOT NULL`), `hubspot_owner_id`, `estado`, `calificacion_del_lead_v2`, `check_a_pricing`, `fecha_creacion`, `fuente_id`
- `papyrus-data.habi_wh_bi.sc_users_hubspot` — resolver `hubspot_owner_id → email`
- `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2` — calificado event-based (`estado_id IN (20, 63)`)

**Limitaciones del refactor:**
- `hubspot_owner_id` en TIG es el owner ACTUAL del deal, no necesariamente el primer asignado. Para deals no reasignados (la mayoría) coincide. Para reasignados, los filtros F3-F5 evalúan al owner actual.
- `estado` en TIG es el estado actual del deal. Lo mismo aplica al filtro original del mart.
- F6 (contacto_digital) y F15 (asignacion_descartes_top) **no pueden aplicarse** con los accesos disponibles. Se renderizan en el panel como locked-disabled.
- F16 (UTC→Colombia) **no aplica**: las fechas en TIG ya están en hora Colombia.

### Mapeo fuente_id → etiqueta

Tal como aparece en el anexo del doc Data&BI:

| fuente_id | Etiqueta |
|---|---|
| 7 | Habimetro |
| 20 | CRM |
| 39 | Broker |
| 3 | WEB |
| 1 | Ventanas |
| 47, 37, 41, 42 | Leadform |
| cualquier otro | Otro |

### Pre-agregación en build_data.py

Cada asignación se reduce a un **bitmask de 14 bits**, uno por flag toggleable, ordenado F3→F15:

```
bit 0 = pasa_f3
bit 1 = pasa_f4
bit 2 = pasa_f5
bit 3 = pasa_f6
bit 4 = pasa_f7
bit 5 = pasa_f8
bit 6 = pasa_f9
bit 7 = pasa_f10
bit 8 = pasa_f11
bit 9 = pasa_f12
bit 10 = pasa_f13
bit 11 = pasa_f14
bit 12 = pasa_f15
bit 13 = reservado (0) — preparación si aparece un F17 a futuro
```

Bitmask `0b1111111111111` (decimal 8191) = "pasa todos los filtros" = mart oficial.

Las asignaciones se agrupan por `(fecha_dia, bitmask, calificado, fuente_label)` y se cuenta. El JSON serializa una fila por combinación observada.

### Estructura `data.json`

```json
{
  "updated_at": "2026-05-11T13:00:00Z",
  "country": "CO",
  "filters": [
    {"id": "F3",  "bit": 0,  "group": "Correo",   "label": "Correo @habi.",                    "tooltip": "..."},
    {"id": "F4",  "bit": 1,  "group": "Correo",   "label": "Excluye agente/delta/call",        "tooltip": "..."},
    {"id": "F5",  "bit": 2,  "group": "Correo",   "label": "Excluye correos hardcoded",        "tooltip": "..."},
    {"id": "F6",  "bit": 3,  "group": "Correo",   "label": "Owners especiales req. contacto digital", "tooltip": "..."},
    {"id": "F7",  "bit": 4,  "group": "Estado",   "label": "Estado: sin pricing incial",       "tooltip": "..."},
    {"id": "F8",  "bit": 5,  "group": "Estado",   "label": "Estado: no gestionado",            "tooltip": "..."},
    {"id": "F9",  "bit": 6,  "group": "Estado",   "label": "Estado: cierre",                   "tooltip": "..."},
    {"id": "F10", "bit": 7,  "group": "Estado",   "label": "Estado: no hay suficientes datos", "tooltip": "..."},
    {"id": "F11", "bit": 8,  "group": "Calidad",  "label": "Calificación no en (N, NH)",       "tooltip": "..."},
    {"id": "F12", "bit": 9,  "group": "Inmueble", "label": "check_a_pricing = 1",              "tooltip": "..."},
    {"id": "F13", "bit": 10, "group": "Inmueble", "label": "fecha_creacion no nula",           "tooltip": "..."},
    {"id": "F14", "bit": 11, "group": "Inmueble", "label": "nid no nulo",                      "tooltip": "..."},
    {"id": "F15", "bit": 12, "group": "Inmo",     "label": "asignacion_descartes_top nula",    "tooltip": "..."}
  ],
  "fuentes": ["Habimetro","CRM","Broker","WEB","Ventanas","Leadform","Otro"],
  "rows": [
    {"d":"2026-05-10","m":8191,"c":1,"f":"Habimetro","n":42},
    {"d":"2026-05-10","m":8191,"c":0,"f":"Habimetro","n":18},
    {"d":"2026-05-10","m":8190,"c":1,"f":"Habimetro","n":3},
    ...
  ]
}
```

Donde en cada `row`:
- `d` = fecha YYYY-MM-DD (UTC-5)
- `m` = bitmask de los flags que cumplió esa cohorte de asignaciones
- `c` = calificado (0/1)
- `f` = etiqueta de fuente
- `n` = count

Estimación de cardinalidad: ~540 días × ~50-100 bitmasks observados × 2 (calificado) × 7 (fuentes) ≈ 50-150k filas → ~3-5 MB JSON sin comprimir, <1 MB gzipped.

### Lógica frontend (consulta)

Hay dos semánticas distintas:
- **Grupo Estado (F7..F10)**: OR estricto dentro del grupo — el deal pasa si su estado coincide con **al menos uno** de los estados marcados por el usuario. Si el usuario apaga los 4, **ningún deal pasa el filtro de estado** (universo se vuelve 0). La UI lo muestra explícitamente con un warning.
- **Resto (F3..F6, F11..F15)**: AND — el deal debe pasar **todos** los filtros marcados.

Esto da comportamiento monótono: cada vez que el usuario apaga un filtro, el universo solo puede crecer (al expandir el set de estados permitidos) o quedarse igual; cada vez que apaga un filtro no-estado, el universo solo puede mantenerse o crecer.

Definiciones (bits 4..7 son F7..F10):
- `STATE_MASK` = bits 4..7 set = `0b00011110000` = decimal 240
- `OTHER_MASK` = los otros 9 bits (F3..F6, F11..F15) = decimal 7951

Para un bitmask `req` con el set activo del usuario:

```
req_state = req & STATE_MASK
req_other = req & OTHER_MASK

deal pasa sii:
  (deal.m & req_other) == req_other     // AND para no-estado
  AND (deal.m & req_state) != 0         // OR para estado (requiere ≥1 match)
```

**Caso degenerado:** si `req_state == 0` (los 4 estados apagados), el segundo `AND` es siempre falso → universo vacío. La UI debe advertirlo en el panel y no dejarlo como sorpresa.

Esto se traduce a:

```
universo_count(d) = sum(n) for rows where
  row.d == d
  AND (row.m & req_other) == req_other
  AND (row.m & req_state) != 0
```

Para "calificado en universo del usuario": misma condición + `row.c == 1`.
Para "fuente X en universo del usuario": misma condición + `row.f == "X"`.

Para la **línea de referencia "mart oficial"** (todos los 13 toggleables ON, `req = 8191`):
```
req_other_mart = 7951
req_state_mart = 240
mart_count(d) = sum(n) where row.d == d AND (row.m & 7951) == 7951 AND (row.m & 240) != 0
```

Para el **efecto marginal de un filtro F**:
- Si F está apagado, el "efecto marginal de activarlo" = `universo_count(req) - universo_count(req | bit_F)`. Para grupos no-estado da un valor ≥ 0 (reduce universo). Para grupo estado puede ser negativo (expandir set de estados aceptados aumenta universo).
- Si F está prendido, el "efecto marginal de apagarlo" se computa simétricamente.
- La tabla muestra el delta absoluto con signo y etiqueta clara: "↓ quita N deals" o "↑ agrega N deals".

### Agregación a granularidad semana/mes

- **Semana ISO** (lunes-domingo, como en los otros tableros): el frontend agrupa `d` a la semana ISO de la fecha. Excluye semana en curso incompleta.
- **Mes**: agrupa a primer día de mes. Excluye mes en curso incompleto.
- **Día**: usa `d` directo. Excluye día en curso (datos pueden estar parciales hasta el cron del día siguiente).

## UX del tablero

### Layout (top-to-bottom)

1. **Header** — back link "← Volver" + título "Leads asignados — Explorador de filtros (CO)" + subtítulo con `updated_at` y conteo total ventana actual

2. **Controles** (sticky o panel fijo arriba):
   - Selector granularidad: chips `Día / Semana / Mes` (default **Semana**)
   - Toggle "Mostrar línea mart oficial" (default ON)
   - Botones rápidos:
     - `Todos on` → activa F3..F15 (= mart oficial, línea ámbar y línea índigo se superponen)
     - `Todos off` → desactiva F3..F15 (= universo crudo, solo F1+F2+F16)
     - `Reset` → vuelve al default = "todos on"

3. **Panel de filtros** (acordeón por grupo, abierto default, columna lateral o arriba del chart según ancho):
   - **Origen** — F1 🔒 (always on, info icon), F2 🔒 (always on, info icon)
   - **Correo** — F3 ☐ F4 ☐ F5 ☐ F6 ☐
   - **Estado** — F7 ☐ F8 ☐ F9 ☐ F10 ☐
   - **Calidad** — F11 ☐
   - **Inmueble** — F12 ☐ F13 ☐ F14 ☐
   - **Inmo** — F15 ☐
   - **Fecha** — F16 🔒 (always on, info icon)
   - Cada toggle con tooltip explicando la lógica del filtro (texto del doc Data&BI)

4. **Chart principal**:
   - 18 períodos en eje X (según granularidad)
   - 2 líneas:
     - **Línea índigo `#818cf8`** (sólida, principal): universo según toggles del usuario
     - **Línea ámbar `#fbbf24`** (dashed, referencia): mart oficial (F3..F15 todos on)
   - Si "todos on" coinciden las dos líneas, la sólida tapa la dashed (esperado)
   - Hover muestra ambos valores + diferencia absoluta + %
   - Último punto resaltado (consistente con otros tableros)

5. **Tabla de breakdowns por filtro** (debajo del chart):
   - Una fila por filtro (F3..F15) + fila final TOTAL = mart oficial
   - Columnas:
     | Filtro | Grupo | Estado actual | Pasaron (período actual) | Excluidos | % Excluido | Efecto marginal | Δ vs período ant |
   - **Efecto marginal**: cuánto más quita ese filtro si lo activas dado el set actual (si ya está activo, qué quita; si está apagado, qué quitaría)
   - **Período actual**: el último de los 18 períodos (más reciente completo)
   - Click en una fila → toggle del filtro (sync con el panel)
   - Sortable por columnas

6. **Bloque calificación** (debajo de la tabla):
   - Mini-chart 1: línea de calificados en el universo del usuario (18 períodos)
   - Mini-chart 2: tasa de calificación (calificado / total) en el universo del usuario
   - Ambos con línea de referencia ámbar dashed para "calificado en mart oficial" (proporcional)

7. **Descomposición por fuente** (al final, opcional v1):
   - Tabla con conteo por fuente para el período más reciente
   - Columnas: Fuente, Universo del usuario, Mart oficial, Diferencia
   - Si hace ruido al MVP, se omite y se agrega en iteración posterior

### Estados y transiciones

- Toggle de un filtro → recalcula universo del usuario, refresca chart principal, mini-charts, tabla
- Cambio de granularidad → reagrupa data en cliente, refresca todo
- Toggle "mostrar línea mart" → muestra/oculta línea ámbar
- Click en fila de tabla → toggle de filtro correspondiente
- Reset → vuelve a "todos on" + granularidad semana

### Accesibilidad y UX

- Tooltips con texto literal del doc Data&BI (el usuario puede leer la lógica SQL exacta)
- Indicador visual claro de filtros locked (F1, F2, F16) vs toggleables
- Responsive básico: en celular el panel de filtros colapsa a un drawer o tabs por grupo

## Auto-update y operación

### Workflow consolidado

Nuevo step en `.github/workflows/update-data.yml`, después de WBR 2.0:

```yaml
- name: Build asignados-filtros data
  run: |
    bq query --use_legacy_sql=false --format=json --max_rows=10000000 \
      < asignados-filtros/query.sql > /tmp/asignados-raw.json
    python asignados-filtros/build_data.py \
      --input /tmp/asignados-raw.json \
      --output asignados-filtros/data.json
  if: always()
```

Commit al final del workflow incluye `asignados-filtros/data.json`.

### Costos BigQuery

- Tablas tocadas: `history` (~5M rows), `deal` (~5.4M rows), `tig` (~4M rows), `historico_estado_v2`, `sc_users_hubspot`
- Scan estimado: 200-500 MB/día (con `WHERE DATE(...) >= CURRENT_DATE - 540`)
- Costo: ~$0.001/día. Negligible.
- Si crece: agregar partición por fecha en el WHERE.

### Pull local

El pull local (`scripts/daily-pull.sh`) ya recoge automáticamente cualquier nuevo `data.json`.

## Componentes y archivos

### Archivos a crear

| Archivo | Tipo | Propósito |
|---|---|---|
| `asignados-filtros/query.sql` | SQL | Replica la lógica del mart desde tablas crudas con flags por filtro |
| `asignados-filtros/build_data.py` | Python | Convierte resultado BQ a JSON pre-agregado con bitmask |
| `asignados-filtros/index.html` | HTML/CSS/JS vanilla | UI completa del tablero |
| `asignados-filtros/data.json` | JSON | Generado por workflow (no manual) |

### Archivos a modificar

| Archivo | Cambio |
|---|---|
| `index.html` (landing root) | Agregar card "Asignados — Explorador de filtros" |
| `.github/workflows/update-data.yml` | Agregar step para `asignados-filtros` después de WBR 2.0 |

## Decisiones explícitamente fuera de alcance v1

- México (los filtros 5 y 6 incluyen correos `@tuhabi.mx` por compartir regla con CO, pero el universo de leads MX no se procesa aquí)
- Drill-down a nivel asignación individual (lista de leads excluidos por filtro X) — útil pero pesado, se deja para v2
- Comparativos contra meta — no aplica a este tablero
- Inversión / CPL / cualquier métrica de spend
- Auto-merge con UTM dict — no es necesario para esta vista
- Selector de país: solo CO disponible, no se muestra selector

## Criterios de éxito v1

1. El tablero se publica en GH Pages y se actualiza diariamente
2. Con "todos on" la línea índigo coincide exactamente con la línea ámbar (mart oficial) — validación de paridad con el mart
3. Con "todos off" el universo es el conjunto de cambios de `hubspot_owner_id` (F1+F2+F16) sin más filtros — debería verse mayor que el mart
4. La diferencia entre universo crudo y mart oficial es consistente con los hallazgos del doc Data&BI (~1k nids/mes en abril 2026)
5. Los efectos marginales en la tabla suman a la diferencia total entre universo crudo y mart oficial (modulo el orden de aplicación)
6. Tiempo de load inicial < 2s, toggle de filtro < 100ms

## Pendientes / próximos pasos posibles (post v1)

- Drill-down: lista de los nids específicos excluidos por cada filtro (útil para Marketing al revisar)
- Replicar para MX cuando aplique
- Exportar tabla de breakdowns a CSV
- Embebido en el WBR o WBR 2.0 como tab "Diagnóstico de filtros"

## Referencias

- Doc Data&BI con la definición oficial: https://docs.google.com/document/d/10-Ig_6DbfVmGIrqxsGvz-9_yprXe8d3mZliIMtZT3us/
- Memoria: `habi/asignados_co_definicion.md` (16 filtros)
- Memoria: `habi/informe_asignados_co_insights.md` (hallazgos post 12-mar)
- Memoria: `habi/tableros/general.md` (convenciones del repo)
- Memoria: `habi/tableros/wbr_2_0.md` (patrón de drill-down)
- Memoria: `habi/tablas_core.md` (tablas BQ)
