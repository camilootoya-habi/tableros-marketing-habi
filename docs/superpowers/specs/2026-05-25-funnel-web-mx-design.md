# Funnel Web MX — Diseño del tablero

**Fecha:** 2026-05-25
**Autor:** Camilo (con Claude)
**Estado:** Spec aprobada, pendiente plan de implementación

## Contexto y problema

El tablero `wbr-2-0` muestra que en **MX → fuente WEB → canal Paid** la tasa **Click → Registro** cayó fuertemente las últimas semanas. El indicador agrega clicks reportados por las plataformas de paid media contra leads creados, sin visibilidad de qué pasa en el medio.

Sospechas a validar:
- Las plataformas (Google/Meta) podrían estar inflando clicks (clicks fantasma, fraude, retries que no llegan al sitio).
- El form pierde gente en pasos específicos que no estamos monitoreando.
- Una zona o tipo de device específico cayó (mobile, una ciudad) y arrastra el promedio nacional.

Este tablero responde **dónde exactamente se cae el funnel y para quién**.

## Alcance del MVP

- **Único país:** México
- **Única fuente:** WEB (`fuente_id = 3` en el mart) — incluye tráfico Paid y Direct
- **Granularidad temporal:** semanal ISO, últimas 20 semanas, default semana cerrada más reciente
- **Out of scope (por ahora):**
  - Colombia (replicaremos cuando MX funcione)
  - Otras fuentes (Estudio Inmueble, Lead Forms, Brokers, Comercial)
  - Granularidad diaria
  - Botón manual de "actualizar"

## Funnel de 13 etapas

Cada etapa cuenta visitantes únicos (o eventos únicos donde aplique) que llegaron a ese estado en la semana. La etapa 2 ("Sesión Segment") cuenta cualquier visitante con al menos un page event del dominio habi.mx esa semana — no se acumula con las etapas siguientes, son grupos solapados (los mismos visitantes pueden contarse en varias etapas si llegaron a varios pasos).

| # | Etapa | Origen del dato | Cluster soportado |
|---|---|---|---|
| 1 | Click reportado | `resumen_inversiones_mkt_mx` (canal_adquisicion='Web') | canal/plataforma |
| 2 | Sesión Segment | `mx_segment_profiles.pages` (cualquier page event del dominio) | canal/plataforma, device |
| 3 | `/formulario-inmueble/inicio` | `mx_segment_profiles.pages` filtrado por path | canal/plataforma, device |
| 4 | `/formulario-inmueble/inmuebles-zona` | ↑ | canal/plataforma, device, **ciudad/zona** (desde aquí en adelante) |
| 5 | `/formulario-inmueble/confirmar-ubicacion-mx` | ↑ | + ciudad/zona |
| 6 | `/formulario-inmueble/datos-inmueble` | ↑ | + ciudad/zona |
| 7 | `/formulario-inmueble/caracteristicas` | ↑ | + ciudad/zona |
| 8 | `/formulario-inmueble/ultimos-detalles` | ↑ | + ciudad/zona |
| 9 | `/formulario-inmueble/sugerencias-de-propiedades` | ↑ | + ciudad/zona |
| 10 | `/formulario-inmueble/contacto` | ↑ | + ciudad/zona |
| 11 | Form submit (backend) | `web_global_api_business` (deal_uuid≠'0', country='MX') | + ciudad/zona |
| 12 | `/formulario-inmueble/felicitaciones` | `mx_segment_profiles.pages` | + ciudad/zona |
| 13 | Lead registrado | `tabla_inmuebles_general` (fuente_id=3) | + ciudad/zona/zona_grande/zona_mediana |

Notas:
- `/editar-sugerencias` es branch opcional, NO es step independiente; se cuenta como visita a `/sugerencias`.
- "Cada paso" = visitante único (`COUNT(DISTINCT anonymous_id)`) — no eventos. Si una persona refresca 3 veces, cuenta 1.

### Tasas de drop entre etapas

Cada par consecutivo de etapas tiene su tasa `n_{i+1} / n_i`. Drops superiores a 50% se resaltan en ámbar como hotspot. La tasa **Click → Sesión** valida si la plataforma está inflando clicks: si pagaste por 1M de clicks pero Segment solo ve 120k sesiones, la plataforma reportó 8x lo real.

## Clusters (filtros)

Tres dimensiones de cluster, aplicables a las etapas que las soportan (ver tabla arriba):

### 1. Canal / Plataforma
- Combinación derivada de UTM del **primer page event del anonymous_id en la semana** (first-touch dentro de la ventana).
- Etiquetas: `Google/Paid`, `Google/Direct`, `Meta/Paid`, `Bing/Paid`, `TikTok/Paid`, `Direct/Direct`, `Otro/Otro`.
- Para etapa "Click reportado": viene del `plataforma` field de `resumen_inversiones_mkt_mx`.
- Para leads sin chain Segment (b.uuid IS NULL): se atribuye vía `campana_mercadeo_original` del lead → UTM dict `bi_mx.registro_unico_utm_mkt_mexico`.

### 2. Device
- Del primer page event del anonymous_id en la semana.
- Etiquetas: `Mobile`, `Desktop`, `Tablet`, `Unknown`.
- Fuentes en Segment: `context_user_agent_data_mobile` (bool) + `context_user_agent_data_platform` (string para distinguir tablet).
- No aplica a etapa "Click reportado".

### 3. Zona del inmueble
- Solo aplica desde etapa `/inmuebles-zona` en adelante (donde el usuario selecciona la ubicación de su inmueble).
- Tres niveles drilldown: **Ciudad** (139 valores) → **Zona grande** (154) → **Zona mediana** (3150).
- Fuente:
  - Para leads: directo de `tabla_inmuebles_general` (`ciudad`, `zona_grande_label`, `zona_mediana_label`).
  - Para form steps intermedios (4-12): extraído del JSON payload `web_global_api_business.data` joined por `backbone_uuid`. Asumimos que la zona se serializa allí cuando el usuario la elige en step 4.
- Default UI muestra top 15 ciudades MX por volumen; el resto se agrega en "Otras".

## Layout visual

### Header
- Pill MX (único país, sin selector)
- Selector de semana (6 píldoras lun-dom, default semana cerrada más reciente)
- Chip "Actualizado hace Xh" (lee `data.updated` ISO)

### Bloque A — Funnel principal
Escalera vertical de 13 barras (una por etapa). Cada barra muestra:
- Nombre de la etapa
- Valor absoluto
- Tasa de drop vs etapa anterior (badge gris si <30%, ámbar si 30-70%, rojo si >70%)
- Barra de longitud proporcional al log del valor (porque la escala click vs lead son órdenes de magnitud distintos)

Click en una barra filtra el Bloque B a esa etapa específica.

### Bloque B — Sparklines 20 semanas
Una sparkline por cada etapa principal (5 hitos: Click, Sesión, /inicio, /contacto, Lead). 12 semanas grises de contexto + 8 activas en color. Último punto resaltado.

### Bloque C — Comparativa por cluster
Tabla con tres pestañas: **Canal/Plataforma**, **Device**, **Zona**.

Filas = valores del cluster (ej. Mobile, Desktop, Tablet).
Columnas = 6 hitos del funnel + tasas Click→Sesión, Sesión→Submit, Submit→Lead.

Click en una fila filtra los Bloques A y B simultáneamente. Combinable con click en etapas del Bloque A.

Para la pestaña Zona: dropdown adicional para elegir nivel (ciudad / zona grande / zona mediana).

### Matriz de cobertura visible
Tooltip o footnote permanente que recuerde qué clusters aplican a qué etapas:

| Cluster | Click | Sesión | /inicio | /inmuebles-zona y posteriores |
|---|---|---|---|---|
| Canal/Plataforma | ✓ | ✓ | ✓ | ✓ |
| Device | – | ✓ | ✓ | ✓ |
| Zona | – | – | – | ✓ |

## Pipeline de datos

### Estructura de archivos
```
funnel-web-mx/
├── index.html
├── data.json          ← auto-update via workflow
├── query_clicks.sql
├── query_sessions.sql
├── query_backbone.sql
├── query_leads.sql
└── build_data.py
```

### Las 4 queries SQL

#### `query_clicks.sql`
- Source: `papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx`
- Filtra `canal_adquisicion='Web'`, `date >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK)`
- Agrupa por (week_start, plataforma) → SUM(spend), SUM(clicks), SUM(impressions)
- Plataforma normalizada a las etiquetas canónicas (Google/Meta/Bing/TikTok/Otro)

#### `query_sessions.sql`
- Source: `sellers-main-prod.mx_segment_profiles.pages`
- Filter: `DATE(timestamp, 'America/Mexico_City') >= DATE_TRUNC(... 140 DAY ...)`, dominio = habi.mx
- Paths del funnel: lista hardcodeada de 11 paths (sesión = cualquier page event; los demás = paths específicos del form)
- Per anonymous_id por semana: extraer primer evento → derivar utm_source, utm_medium, device (mobile/desktop/tablet)
- Output: (week, stage, plataforma_canal, device) → COUNT(DISTINCT anonymous_id)
- Stage especial "session" = cualquier path; los demás = path específico

#### `query_backbone.sql`
- Source principal: `sellers-main-prod.top_funnel.web_global_api_business` WHERE `country='MX'`, `created_at >= ...`
- Form start: COUNT(DISTINCT uuid) por (week, ...)
- Form submit: COUNT(DISTINCT uuid) WHERE `deal_uuid != '0'`
- Join con `mx_segment_profiles.select_content` por `backbone_uuid = uuid` para enriquecer con anonymous_id → UTM + device del first-touch
- Extraer `ciudad`, `zona_grande`, `zona_mediana` del JSON `data` (verificar estructura en implementación)
- Output: (week, stage, plataforma_canal, device, ciudad) → counts

#### `query_leads.sql`
- Source: `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` WHERE `fuente_id = 3`, `fecha_creacion >= ...`
- Join con `habi_db_property` para zona/ciudad si no están directamente en `tabla_inmuebles_general` (verificar — están allí según schema check)
- Join con backbone+select_content+pages para UTM/device del visitante original (left join, fallback a UTM dict por `campana_mercadeo_original` cuando el chain falla)
- Output: (week, plataforma_canal, device, ciudad, zona_grande, zona_mediana) → n_leads, n_calificados (state 20/63), n_asignados (mart)

### `build_data.py`

Recibe 4 paths JSON (output de las queries) + 1 path output. Produce:

```json
{
  "updated": "2026-05-25T15:40:00Z",
  "weeks": ["2025-12-29", ..., "2026-05-18"],
  "stages": [
    {"id": "click", "label": "Click reportado", "supports": ["canal_plat"]},
    {"id": "session", "label": "Sesión Segment", "supports": ["canal_plat","device"]},
    {"id": "inicio", "label": "/inicio", "supports": ["canal_plat","device"]},
    {"id": "zona", "label": "/inmuebles-zona", "supports": ["canal_plat","device","ciudad","zona_grande","zona_mediana"]},
    {"id": "confirmar_ubicacion", "label": "/confirmar-ubicacion-mx", "supports": [...]},
    {"id": "datos_inmueble", "label": "/datos-inmueble", "supports": [...]},
    {"id": "caracteristicas", "label": "/caracteristicas", "supports": [...]},
    {"id": "ultimos_detalles", "label": "/ultimos-detalles", "supports": [...]},
    {"id": "sugerencias", "label": "/sugerencias-de-propiedades", "supports": [...]},
    {"id": "contacto", "label": "/contacto", "supports": [...]},
    {"id": "submit", "label": "Form submit", "supports": [...]},
    {"id": "felicitaciones", "label": "/felicitaciones", "supports": [...]},
    {"id": "lead", "label": "Lead registrado", "supports": [...]}
  ],
  "by_week": {
    "2026-05-18": {
      "totals": { "click": 1000000, "session": 120000, ..., "lead": 1200 },
      "by_canal_plat": { "Google/Paid": { stage_id: count, ... }, ... },
      "by_device": { "mobile": { stage_id: count, ... }, ... },
      "by_ciudad": { "CDMX": { stage_id: count, ... }, ... },
      "by_zona_grande": { ... },
      "by_zona_mediana": { ... }
    },
    ...
  }
}
```

### Workflow CI

Agregar al `.github/workflows/update-data.yml` consolidado:
- 4 nuevos steps `bq query ... > /tmp/wfmx_{name}.json`
- 1 step `python3 funnel-web-mx/build_data.py /tmp/wfmx_clicks.json /tmp/wfmx_sessions.json /tmp/wfmx_backbone.json /tmp/wfmx_leads.json funnel-web-mx/data.json`
- Agregar `funnel-web-mx/data.json` al `git add` del commit final
- Reutilizar mismo cron `0 */4 * * *`

## Atribución — reglas claras

1. **Sesiones y form steps**: UTM + device del **primer page event del anonymous_id en la semana**. Define el "canal_plat" y "device" para todas las visitas de ese anonymous_id esa semana.

2. **Form starts/submits desde backbone**: chain `web_global_api_business.uuid` → `select_content.backbone_uuid` → `select_content.anonymous_id` → primer `pages` event de esa semana → UTM + device. Si el chain falla (no hay select_content match), se categoriza como `Direct/Direct` + `Unknown` device.

3. **Leads**: prioridad: (a) chain Segment como arriba; (b) si chain falla, atribuir vía `tabla_inmuebles_general.campana_mercadeo_original` → UTM dict `registro_unico_utm_mkt_mexico` para canal_plat (device queda Unknown).

4. **Zona**: solo se atribuye desde la etapa `/inmuebles-zona` en adelante. Fuente: payload JSON de `web_global_api_business.data` (a verificar en implementación) o `tabla_inmuebles_general` para los que llegaron a lead.

## Frontend — comportamiento del UI

- **Default**: semana más reciente cerrada, sin filtros activos → muestra el funnel nacional completo.
- **Click en etapa del Bloque A**: el Bloque B (sparklines) cambia foco a esa etapa con un highlight; el Bloque C resalta la columna correspondiente.
- **Click en fila del Bloque C**: filtra Bloques A y B. Filtros son aditivos (Mobile + CDMX → solo mobile en CDMX).
- **Cambio de pestaña en Bloque C**: cambia el cluster activo (Canal/Plataforma → Device → Zona). El filtro activo en otra pestaña se mantiene si hace sentido (ej. Mobile sigue activo al cambiar a Zona).
- **Hover en cualquier barra/celda**: tooltip con valor absoluto, % del total semanal, y delta vs semana anterior.

## Tema visual

Reutiliza el tema compartido de los tableros marketing:
- BG `#0f172a`, cards `#1e293b`, borders `#334155`
- Acento índigo `#818cf8`
- Texto `#f8fafc / #e2e8f0 / #94a3b8`
- Mismo favicon megáfono
- Back link "← Volver (Tableros Marketing Sellers)" al inicio del body
- Mismas convenciones de header/spacing que `wbr-2-0`

## Estimación de costos BQ

| Query | Bytes/run estimados | Runs/día | GB/mes |
|---|---|---|---|
| query_clicks | ~50 MB | 6 | ~9 |
| query_sessions | ~3-5 GB (segment.pages pesada) | 6 | ~720 |
| query_backbone | ~1 GB | 6 | ~180 |
| query_leads | ~200 MB | 6 | ~36 |
| **Total** | | | **~945 GB/mes** |

Cerca del límite de 1 TB free. Mitigaciones:
- Verificar partición de `mx_segment_profiles.pages` y forzar filtro de partición
- Si excede, bajar cron a cada 6h o 8h (sigue cumpliendo el objetivo lunes-mañana)
- Considerar materializar una vista weekly de `segment.pages` que reduzca el scan

## Riesgos y validaciones pre-implementación

1. **Partición de `mx_segment_profiles.pages`**: confirmar que tiene partición por timestamp; sin ella el costo se dispara.
2. **Estructura de `web_global_api_business.data` JSON**: verificar que incluye `ciudad`/`zona` para los pasos pre-lead. Si no, la atribución de zona solo funciona desde leads.
3. **Stability de `select_content` con `backbone_uuid`**: confirmar % de sessions que tienen el evento. Si es bajo (<70%), muchas atribuciones quedarán como "Direct/Direct/Unknown".
4. **`canal_adquisicion='Web'` en `resumen_inversiones_mkt_mx`**: validar que captura todo el spend WEB Paid (no se queda algo en `Habimetro` o `Calculadora`).
5. **Branching opcional `/editar-sugerencias`**: confirmar con producto que no es step canónico.
6. **Cross-device sessions**: visitas en mobile + completar en desktop crean dos anonymous_id distintos. Se acepta como limitación; medida via leads totales no se afecta, solo la atribución de device.

## Métricas de éxito

El tablero es exitoso si:
- En menos de 30 segundos, una persona puede identificar **en qué etapa específica** se cae el funnel para una semana dada.
- Permite responder: "¿la caída en click→registro es real o son clicks fantasma?" mirando la tasa Click→Sesión.
- Permite responder: "¿la caída es nacional o concentrada en una zona/device?" mirando el Bloque C.
- Datos disponibles automáticamente cada lunes a más tardar a las 09:00 hora CDMX.

## Out of scope

- Atribución multi-touch (solo first-touch en la semana)
- Análisis cohorte: seguir un visitante entre semanas
- Predicciones / forecasting
- Botón manual de actualizar (se descartó)
- Soporte CO (se replicará después de validar MX)
- Otras fuentes no-WEB
- Granularidad diaria

## Próximos pasos

1. Aprobación de este spec por el usuario.
2. Invocar `writing-plans` para construir el plan de implementación detallado (tareas por SQL, build_data, frontend, workflow).
3. Implementar siguiendo el plan, con review checkpoints.
