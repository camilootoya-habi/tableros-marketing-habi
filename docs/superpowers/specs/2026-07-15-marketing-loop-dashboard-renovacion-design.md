# Renovación tablero "Marketing Loop sellers" — Diseño

**Fecha:** 2026-07-15
**Estado:** aprobado (brainstorming) — pendiente review del spec antes del plan
**Tablero:** `marketing-loop/` en el hub `tableros-marketing-habi` · live https://camilootoya-habi.github.io/tableros-marketing-habi/marketing-loop/

---

## 1. Propósito

Renovar el tablero para alinearlo al **nuevo proyecto `marketing-loop-sellers`** (`~/habi/marketing-loop-sellers`), que movió el estado a **Neon** y usa el **mart `infobib_gold`** como fuente de verdad. Hoy el tablero lee de **Sheets + CSVs de ledgers del repo privado + reliquias del señuelo** (geo/address health), desalineado con el nuevo funcionamiento. La renovación re-cablea todo a **Neon + mart + Meta**, elimina lo obsoleto, y agrega indicadores de entrega/errores que hoy no existen.

## 2. Decisiones (tomadas en brainstorming)

- **Alcance: MX primero.** CO queda como está / "pendiente" (sin acceso al mart CO, el proyecto nuevo es MX-first). No se elimina CO del tablero, solo no es el foco.
- **Re-cableo TOTAL a Neon + mart** (no parcial). Se elimina Sheets, CSVs de ledgers y geo/address health.
- **Granularidad por defecto = "día"** en todos los selectores de granularidad.
- Se mantiene el patrón visual del hub (tablero estático, `fetch('data.json')`, generado por el cron `update-marketing-loop.yml`).

## 3. Arquitectura de datos — el re-cableo

`build_data.py` se reestructura en **4 lectores**. La llave que une envío ↔ resultado es **`send_log.message_id ⋈ mart.message_id`** (atribución exacta de entrega/error por intento, en tiempo real, sin depender del lag diario del mart para el join lógico).

| Lector | Acceso | Qué provee |
|---|---|---|
| **Neon** (psycopg) | secret **`NEON_DATABASE_URL`** nuevo en el cron del hub | `send_log` (intentos, accepted, message_id, template, nid, deal_id, attempted_at), `recreation` (old_nid→new_deal, state_at_creation, success, created_at), `contact_status` (state, attempt_count, timestamps por teléfono) |
| **Mart** BQ `papyrus-master.infobib_gold_mx.mart_infobip_messages_daily_mx` | bq (ADC), filtrado a nuestras líneas | outbound: `message_id/status/error_name/template/seen_at/send_at_raw`; inbound: `respuesta_cliente/from_number/send_at_raw` |
| **Meta Graph** | `META_ACCESS_TOKEN` (ya existe) | calidad/tier/estado/review/throughput de la línea |
| **BQ tig/hubspot** | bq (ADC) | estado actual del lead (`id_last_state`), trimestre de creación (`fecha_creacion`), completitud, impacto en asignados |

**Líneas MX:** activa `5215595483481` + vieja `5215590883423` (para histórico). **Ventana por defecto del embudo:** 7 días completos (excluye hoy); las tablas con selector arrancan en **día**.

## 4. Especificación indicador por indicador

Notación: 🟢 mantener · 🔵 re-trabajar · 🟣 nuevo · 🔴 eliminar.

### 4.1 🟢 Salud del canal (Meta)
`linea_meta(MX)` — Graph `{WABA}/phone_numbers` (quality_rating→HIGH/MEDIUM/LOW, messaging_limit_tier, status, throughput) + `{WABA}` account_review_status. **Fix:** si Graph no devuelve `tier`, respaldo Infobip **etiquetado** ("tier vía Infobip"). Fuente por defecto: Meta.

### 4.2 🔵 Embudo de salida + entrega
Por bucket de fecha (default día): **Intentos** (count send_log) → **Aceptados** (send_log.accepted) → **Entregados** (⋈mart status='delivered') → **Leídos** (mart seen_at poblado) → **Respondieron** (teléfono del send_log presente en mart inbound) → **Interesados** (payload INTERESADO) → **Recreados** (recreation) → **Calificados** (estado backbone 20/63).
Tasas: `send_rate=aceptados/intentos` · `delivery_rate=entregados/intentos` · `read_rate=leídos/entregados` · `respond_rate=respondieron/entregados`.

### 4.3 🟣 Errores de entrega por tipo (NUEVO)
`send_log.message_id` de la ventana ⋈ mart → bucketear `error_name`:
`entregado (code 0)` · `frequency capping (7032)` · `device-error (7020)` · `inválido (351)` · `template (7009)` · `bloqueado operador (566)` · `otro`. Se muestra el **% sobre intentos**, con selector por día. (Refleja el hallazgo real: entrega ~44%, freq-cap ~36%, device-error ~19%.)

### 4.4 🟢 Read/respond rate por hora
`por_hora` (ya sobre el mart) — mantener.

### 4.5 🔵 Respuestas por tipo (re-cablear a mart)
mart inbound de nuestras líneas → **regex sobre `respuesta_cliente`** (misma lógica que `parse_inbound` del proyecto: `activacion_NewLeads_(INTERESADO|YAVENDIÓ)_<nid>` + texto libre). Buckets: **INTERESADO · ya vendió · baja · texto libre (respondio_otro)**. Conteo + `respond_rate = respuestas/entregados`. **Elimina la dependencia de Sheets.**

### 4.6 🟣 A/B de plantillas (NUEVO — scaffold)
`send_log.template` ⋈ mart por message_id → por template: **enviados · delivery% · respond_rate**. Hoy solo `reactivacion_sellers_mx_v1_jul26`; la v2 (`reactivacion_sellers_mx_v2_oferta_jul26`) aparece automáticamente cuando tenga envíos. Sección visible pero comparativa "se activa" al haber ≥2 templates con datos.

### 4.7 🔵 Calidad por antigüedad del lead original (expandir)
Para cada `send_log` (nid, message_id): BQ tig `nid → trimestre de fecha_creacion` (una query batch) + mart `message_id → status/error`. Agregado **por trimestre de creación del NID**: **enviados · delivery% · freq-cap% · device-error%**. Muestra la correlación antigüedad→device-error (verificado: 2022=43% device → 2026=0%).

### 4.8 🔵 Funnel del programa + outcome de dedup (NUEVO sub-indicador)
De **Neon `recreation`**, por bucket `created_at` (día default): **recreados** · **% en Duplicado** (`state_at_creation=1`) vs **calificado** (`=20`). El `state_at_creation` es el estado del deal NUEVO al crearse = outcome de dedup (mide el 77% Duplicado histórico y si el fix de tech baja eso).

### 4.9 🔵 Antifunnel — estado actual de recreados
`recreation.new_deal_id` → BQ tig `id_last_state` (estado ACTUAL) → distribución por estado, bucketeada por `created_at` (día default).

### 4.10 🟣 Estado de contacto de la base (NUEVO)
De **Neon `contact_status`**: distribución por `state` (enviado / reinteresado / ya_vendio / baja / respondio_otro) — el ciclo de vida de los ~17k+ contactos. Opcional: tendencia por `last_sent_at` (día).

### 4.11 🟢 Se mantienen (BQ, siguen válidos)
- **Completitud de datos** (`query_completitud.sql`) sobre leads creados.
- **Impacto en asignados** (BQ) — contribución del loop.
- **Definición de la base** (texto estático) → actualizar: piso creación **2023-01-01**, fuentes **3 (WEB) + 47 (Lead Forms)**, techo hoy−180d, calificado por backbone, con dirección, descarte duro, dedup en cadena.
- **Plantillas aprobadas** → hacer **dinámico** desde Infobip (`/whatsapp/2/senders/{sender}/templates`): lista v1 (APPROVED) + v2 (estado actual). 
- **Documentación del plan** (estático).

### 4.12 🔴 Se eliminan
- `geo_health` + `address_health` (reliquias del señuelo; el proyecto ya no usa receta señuelo).
- Lectores de **Sheets** (`resp_rows`, `base_enviada`, `SS_RESP`, `SS_ENV`).
- Lectores de **CSVs de ledgers** del repo privado (`fetch_private_csv`, `LEDGER_PATHS`, `SENT_PATH`) — reemplazados por Neon.
- `comparativa` / `ciclo` (consolidados en el embudo nuevo).
- Explorador de la base CO: se conserva pero fuera de foco (MX-first).

## 5. Frontend (`index.html`)

- Cada sección con selector de granularidad **inicia en "día"** (cambiar el default actual).
- Renderizar las secciones nuevas (errores por tipo, A/B templates, estado de contacto, outcome de dedup) siguiendo el patrón de cards/tablas/charts existente.
- Quitar el render de geo/address health y de las secciones eliminadas.
- Mantener el patrón del hub: estático, `fetch('data.json')`, sin dependencias externas nuevas en el front.

## 6. Dependencias y operación

- **Nuevo secret en el hub:** `NEON_DATABASE_URL` (read-only idealmente) para que `build_data.py` lea Neon desde el cron. Agregar `psycopg[binary]` al setup del cron.
- El cron `update-marketing-loop.yml` (cada ~4h) sigue igual; solo cambia qué lee `build_data.py`.
- Neon free tier: una lectura cada 4h no presiona límites de conexión.
- ⚠ `build_data.py` arma `data.json` al correr; regenerar a mano requiere las llaves (Neon + Meta + bq) o dejar que el cron lo reconstruya (gotcha ya conocido del tablero).

## 7. Gaps / no-goals

- **CO**: sus indicadores nuevos (entrega/errores/respuestas del mart) quedan vacíos/"pendiente" hasta acceso al mart CO. No se invierte en CO ahora.
- **A/B**: la comparación real arranca cuando Meta apruebe la v2 y tenga envíos.
- **No-goals**: no se rediseña el patrón visual del hub, no se tocan otros tableros, no se agrega CO nuevo.

## 8. Testing / validación

- `build_data.py` renovado: correr local con las llaves (Neon + bq + Meta) y validar que `data.json` trae las keys nuevas con datos reales (embudo, errores por tipo, respuestas del mart, cohorte con errores, contact_status).
- Cotejar cifras clave contra lo medido hoy vía API de logs de Infobip (entrega ~44%, freq-cap ~36%, device ~19%) — deben cuadrar.
- Revisar en localhost antes de push (regla del hub: localhost → PR → Camilo mergea; NO push directo a main).
