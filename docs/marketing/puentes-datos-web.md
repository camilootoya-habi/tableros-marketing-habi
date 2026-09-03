# Puentes de datos del funnel WEB (CO + MX)

Know-how extraído de `funnel-fuentes/` (CO) y `funnel-web-mx/` (MX) antes de retirarlos
del hub (2026-09-02). Ambos tableros se consolidaron en la hoja **Funnel WEB** de
`tablero-marketing/`. Este documento conserva lo que costó descubrir; el SQL vivo está
en esa hoja.

---

## 1. Pasos del formulario de registro (Segment `pages`)

El formulario WEB es una SPA con una URL por paso. El orden **no es el mismo en los dos
países** y el primer paso tiene nombre distinto — este es el error clásico al portar
lógica de un país al otro.

### Colombia — `co_segment_profiles.pages`, tz `America/Bogota`

| Paso canónico | `context_page_path` |
|---|---|
| `direccion` (tope real del form) | `/formulario-inmueble/direccion` |
| `zona` | `/formulario-inmueble/inmuebles-zona` · `/confirmar-ubicacion` · `/sugerencias` |
| `datos_inmueble` | `/formulario-inmueble/datos-inmueble` |
| `caracteristicas` | `/formulario-inmueble/caracteristicas` |
| `ultimos_detalles` | `/formulario-inmueble/ultimos-detalles` |
| `contacto` | `/formulario-inmueble/contacto` |
| `felicitaciones` | `/formulario-inmueble/felicitaciones` |

### México — `mx_segment_profiles.pages`, tz `America/Mexico_City`

| Paso canónico | `context_page_path` |
|---|---|
| `inicio` (tope real del form) | `/formulario-inmueble/inicio` |
| `zona` | `/formulario-inmueble/inmuebles-zona` |
| `confirmar_ubicacion` | `/formulario-inmueble/confirmar-ubicacion-mx` ⚠️ sufijo `-mx` |
| `datos_inmueble` | `/formulario-inmueble/datos-inmueble` |
| `caracteristicas` | `/formulario-inmueble/caracteristicas` |
| `ultimos_detalles` | `/formulario-inmueble/ultimos-detalles` |
| `sugerencias` | `/formulario-inmueble/sugerencias-de-propiedades` · `/editar-sugerencias` |
| `contacto` | `/formulario-inmueble/contacto` |
| `felicitaciones` | `/formulario-inmueble/felicitaciones` |

⚠️ **Diferencias que rompen un port ingenuo:**
- Tope del form: CO `direccion`, MX `inicio`.
- Confirmar ubicación: MX lleva sufijo `-mx`; CO no.
- Sugerencias: CO las agrupa dentro de `zona`; MX es un paso propio con 2 URLs.
- MX filtra además por `context_page_url LIKE '%habi.mx%'` para excluir otros dominios.

### `felicitaciones` = registro completado
Es el paso **posterior** al OTP y el único que representa registro terminado desde la
perspectiva del usuario. **No usar "deal creado en backbone" como registro**: el deal se
crea *antes* del OTP, así que `/contacto → deal` da ~99% en ambos países y esconde por
completo la fricción del formulario. Medido 2026-09-01.

---

## 2. Puente `anonymous_id → nid` (chain UUID)

Cómo se cruza el mundo de Segment (anónimo) con el de negocio (`nid`). Cadena de 4 saltos:

```
anonymous_id
  → select_content.backbone_uuid          -- {co,mx}_segment_profiles.select_content
  → web_global_api_business.uuid          -- top_funnel.web_global_api_business
  → .deal_uuid
  → tabla de negocio por país → nid
```

Tabla de negocio por país:
- **CO:** `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` (`uuid` → `nid`)
- **MX:** `sellers-main-prod.mx_rds_staging.habi_db_property_deal` (`uuid` → `nid`)

**Gotchas del puente:**
- `select_content` tiene N filas por `anonymous_id`. Hay dos estrategias y **no dan lo
  mismo**: `funnel-fuentes` (CO) ancla por **mismo día** (`DATE(sc.timestamp) = d_form`),
  mientras que EXP-011 usa el **último** (`QUALIFY ROW_NUMBER() OVER (PARTITION BY
  anonymous_id ORDER BY received_at DESC) = 1`). El ancla por día es más estricta y evita
  atribuir un registro viejo a una sesión nueva; el "último" recupera más volumen. Elegir
  según si se mide *cohorte de sesión* o *cobertura*.
- `web_global_api_business` también puede tener varias filas por `uuid` → dedupe con
  `QUALIFY ROW_NUMBER() OVER (PARTITION BY uuid ORDER BY deal_uuid) = 1`.
- El chain **no resuelve siempre**. `funnel-fuentes` medía explícitamente el residuo
  (`completions_no_deal_daily`: llegó a `/felicitaciones` pero el chain no encontró deal
  el mismo día) — vale la pena conservar esa fila como control de calidad, no descartarla.
- ⚠️ **En MX el chain tenía ~1,7% de cobertura** y por eso `funnel-web-mx` NO lo usaba:
  atribuía por diccionario UTM (`campana_mercadeo_original` contra
  `bi_mx.registro_unico_utm_mkt_mexico`). Antes de usar chain UUID en MX, medir cobertura.

---

## 3. Atribución de canal / plataforma / device

### Desde Segment (sesiones, MX — `funnel-web-mx`)
El **primer** page event del `anonymous_id` **en la semana** define UTM y device
(`ARRAY_AGG(... ORDER BY ts LIMIT 1)[OFFSET(0)]`). Campos:
`context_campaign_utm_source`, `context_campaign_utm_medium`,
`context_user_agent_data_mobile`, `context_user_agent_data_platform`.

Reglas de canal (orden importa — paid antes que organic):
- `google` + medium ∈ (cpc, paid, ppc, paidsearch) → `Google/Paid`; si no → `Google/Organic`
- source ∈ (facebook, instagram, meta, fb, ig) + medium paid → `Meta/Paid`; si no → `Meta/Organic`
- `bing` → `Bing/Paid` · `tiktok` → `TikTok/Paid` · vacío → `Direct/Direct` · resto → `Otro/Otro`

Device: `is_mobile = TRUE` + platform `ipad` → `tablet`; `TRUE` → `mobile`;
`FALSE` → `desktop`; `NULL` → `unknown`.

### Desde negocio (leads, MX)
`tabla_inmuebles_general.campana_mercadeo` → join a
`bi_mx.registro_unico_utm_mkt_mexico` por `campana_mercadeo_original` → `mkt_platform` /
`mkt_channel_medium`. **Device no existe de este lado** (se rellena `unknown`), así que
sesiones y leads no son comparables por device — solo por canal.

### Clasificación de sub-fuente (CO — `funnel-fuentes`)
Help-to-sell vs web puro se separaba por marcas en la URL/referrer, no por `fuente_id`:
```sql
CASE WHEN context_page_url LIKE '%utm_content=help_to_sell%'
       OR context_page_referrer LIKE '%ayudaventas-habi-web.vercel.app%'
     THEN 'help_to_sell' ELSE 'web_puro' END
```

---

## 4. Tope de funnel y etapas de negocio

- **Asignados (canónico, el que usa Data para el WBR):**
  `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`,
  filtrando `pais` + `fuente_id_tig = 3` (WEB).
- **Calificado — usar histórico, no snapshot.** Primera entrada a estado 20/63:
  - CO: `co_rds_staging.habi_db_tabla_historico_estado_v2` (join `negocio_id`)
  - MX: `mx_rds_staging.habi_db_history_state` (join `deal_id`, campo `date_create`)
- **Registros por fuente:** `papyrus-data.habi_wh_bi.tabla_inmuebles_general` (CO) /
  `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` (MX), `fuente_id = 3` para WEB.
  ⚠️ Son **proyectos GCP distintos** por país, mismo nombre de dataset y tabla.
- **Funnel completo hasta cierre:** ver `habi/funnel_tablas_completas` — MM CO
  `papyrus-data.habi_wh_bi.funnel_diarios_col` (`valor`), MM MX
  `bi_mx.seguimiento_funnel_mex` (`valor`).

---

## 5. Capa OTP (nueva, no existía en ninguno de los dos tableros)

Eventos en `{co,mx}_segment_profiles.user_interaction`, campo `event_name`:
`otp_modal_shown` · `otp_request_sent` · `otp_validation_success` ·
`otp_validation_error` · `otp_validation_attempts_exhausted` · `otp_resend_requested` ·
`otp_resend_limit_reached` · `otp_request_failed` · `otp_validation_network_error`.

Espejo en la DB de negocio: `{co,mx}_rds_staging.habi_sellers_deal_additional`,
campo JSON `meta.otp_validated` (`JSON_VALUE(meta, "$.otp_validated")`), join
`deal_id` → tabla de negocio → `nid`.

⚠️ **Hueco de instrumentación:** quien abandona el modal sin validar deja
`otp_validated` en **NULL**, indistinguible de quien nunca vio OTP. Solo el que falla
explícitamente queda en `false`. Por eso el conteo de "no verificados" por la DB
subestima mucho (334 CO / 601 MX contra ~2.000 requests/semana). Para medir abandono real
hay que usar los eventos de Segment, no el campo de negocio.

**Regímenes conocidos (para marcar en cualquier serie):**
| Periodo | Régimen |
|---|---|
| antes de 2026-05-22 | sin OTP |
| 2026-05-22 → 2026-07-13 | A/B (share aleatorio del funnel) |
| 2026-07-14 → 2026-08-19 | OTP al 100% (rollout EXP-011) |
| 2026-08-03 → 2026-08-14 | ⚠️ degradado en MX (budget AWS SNS) |
| 2026-08-20 | ⚠️ falla total (requests sin entrega) |
| 2026-08-21 → re-encendido | apagado |

Contexto del experimento: `juanquinones-habi/product-sparring`,
`experiments/2026-Q3/automatizacion/EXP-011-ALL-MM-PERF-20260714-otp-web-limpieza-leads.md`.

---

## 6. ⚠️ Gotcha de zona horaria al resolver el chain por fecha

`DATE(<TIMESTAMP>)` en BigQuery evalúa en **UTC**, no en la zona del país. Si el
recorrido se ancla con `DATE(MIN(timestamp))` y el `select_content` se ancla con
`DATE(timestamp, 'America/Mexico_City')`, se están comparando **dos calendarios
distintos**: una visita de las 22:00 CDMX ya es el día siguiente en UTC.

Efecto medido (2026-09-02, semana del 24-ago MX): la ventana del join se corría un día
para todo el tráfico nocturno. Resultado doble —
- **falsos positivos**: 4 recorridos de solo `Inicio` aparecían creando lead (era el lead
  que esa persona creó al volver al día siguiente);
- **falsos negativos**, mucho peores: se perdían los leads legítimos de la gente que
  llena el formulario de noche. El conteo total pasó de **1.018 → 1.410 leads (+38%)** al
  corregirlo.

**Regla:** propagar la fecha **local** (`DATE(timestamp, '<tz>')`) desde el CTE base hasta
el join, y nunca re-derivarla con `DATE()` sobre un TIMESTAMP más adelante.

Con el bug corregido, la señal del OTP queda limpia:

| Recorrido | Visitantes | Crean lead | % |
|---|---:|---:|---:|
| Solo `Inicio` | 34.401 | 0 | 0,0% |
| Termina en `Contacto` | 534 | 42 | **7,9%** |
| Pasa de `Contacto` | 489 / 169 / 118 | 488 / 168 / 118 | **~100%** |

Es decir: **pasar el OTP es prácticamente binario**. Quien lo supera genera lead casi
siempre; quien se queda en `Contacto`, casi nunca.
