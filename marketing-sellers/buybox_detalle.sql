-- Hoja "Error de Buybox — detalle" · lead por lead, últimos 30 días (CO y MX)
--
-- Es el drill-down de la tabla "Error de Buybox — en qué estado Inmo quedaron" de la hoja
-- de Calificación. Ahí se ve el agregado; aquí se ve quién.
--
-- DEFINICIÓN, la misma que usa `query.sql` para la fila `cal_mm_no_inmo`:
--   un lead está en Error de Buybox si su estado ACTUAL de Market Maker está en (20, 63)
--   —o sea, califica para MM— y NUNCA pasó por el estado 20 de Inmobiliaria. Califica
--   para uno y no para el otro, que es justo lo que no debería pasar si el buy box de los
--   dos productos estuviera bien calibrado.
--
-- FUENTES POR PAÍS
--   Estado actual y nid  → CO: `co_rds_staging.habi_db_tabla_negocio_inmueble`
--                          MX: `mx_rds_staging.habi_db_property_deal`
--   Historia Inmo        → `{co,mx}_rds_staging.habi_db_history_state_real_estate`, state_id = 20
--   Fuente del lead      → `tabla_inmuebles_general` del país
--   Pipeline y owner     → `hubspot.historical` (propiedad='pipeline' y 'hubspot_owner_id'),
--                          tomando el ÚLTIMO valor de cada uno. `hubspot_owner_id` guarda
--                          el email del comercial, no un id numérico.
--
-- VENTANA: leads creados en los últimos 30 días. Es un tablero de trabajo, no una serie:
--   la idea es poder abrir la lista y llamar a alguien, no ver tendencia.
--
-- ⚠️ El estado de MM es el ACTUAL, no el del momento de calificar. Un lead que calificaba
--   y ya no, no aparece aquí — eso lo mide la fila "Error de consistencia MM" de la hoja
--   de Calificación, que es otra cosa.
--
-- Salida: una fila por lead. {c, nid, fecha_creacion, fuente, pipeline, owner,
--                             estado_mm, estado_inmo}

WITH
  negocios AS (
    SELECT
      'Colombia' AS c, CAST(t.nid AS STRING) AS nid, t.id AS biz_id,
      t.last_estado_id AS estado_mm_id, t.last_state_id_real_estate AS estado_inmo_id
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` t
    WHERE t.nid IS NOT NULL
    UNION ALL
    SELECT
      'México', CAST(t.nid AS STRING), t.id,
      t.last_state_id, t.last_state_id_real_estate
    FROM `sellers-main-prod.mx_rds_staging.habi_db_property_deal` t
    WHERE t.nid IS NOT NULL
  ),

  -- ¿alguna vez llegó al estado 20 de Inmobiliaria?
  cal_inmo AS (
    SELECT DISTINCT n.c, n.nid
    FROM `sellers-main-prod.co_rds_staging.habi_db_history_state_real_estate` h
    JOIN negocios n ON n.c = 'Colombia' AND n.biz_id = h.deal_id
    WHERE h.state_id = 20
    UNION DISTINCT
    SELECT DISTINCT n.c, n.nid
    FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state_real_estate` h
    JOIN negocios n ON n.c = 'México' AND n.biz_id = h.deal_id
    WHERE h.state_id = 20
  ),

  -- La TIG ya trae el estado de MM como TEXTO, así que no hace falta un catálogo aparte
  -- (`papyrus-data.habi_db.tabla_estado` no existe).
  tig AS (
    SELECT 'Colombia' AS c, CAST(nid AS STRING) AS nid, DATE(fecha_creacion) AS fecha_creacion,
           COALESCE(NULLIF(TRIM(fuente), ''), '(sin fuente)') AS fuente,
           COALESCE(NULLIF(TRIM(estado), ''), '(sin estado)') AS estado_txt
    FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general`
    WHERE nid IS NOT NULL AND fecha_creacion IS NOT NULL
      AND DATE(fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    UNION ALL
    SELECT 'México', CAST(nid AS STRING), DATE(fecha_creacion),
           COALESCE(NULLIF(TRIM(fuente), ''), '(sin fuente)'),
           COALESCE(NULLIF(TRIM(estado), ''), '(sin estado)')
    FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general`
    WHERE nid IS NOT NULL AND fecha_creacion IS NOT NULL
      AND DATE(fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  ),

  -- último pipeline y último owner conocidos, de `historical`
  hs AS (
    SELECT
      CAST(nid AS STRING) AS nid,
      ARRAY_AGG(IF(propiedad = 'pipeline', valor, NULL) IGNORE NULLS
                ORDER BY fecha DESC LIMIT 1)[SAFE_OFFSET(0)]          AS pipeline_id,
      ARRAY_AGG(IF(propiedad = 'hubspot_owner_id', valor, NULL) IGNORE NULLS
                ORDER BY fecha DESC LIMIT 1)[SAFE_OFFSET(0)]          AS owner
    FROM `sellers-main-prod.hubspot.historical`
    WHERE propiedad IN ('pipeline', 'hubspot_owner_id')
      AND nid IS NOT NULL
      AND fecha >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 120 DAY))
    GROUP BY nid
  )

SELECT
  n.c,
  n.nid,
  t.fecha_creacion,
  t.fuente,
  COALESCE(p.label, CONCAT('(', IFNULL(hs.pipeline_id, 'sin pipeline'), ')')) AS pipeline,
  IFNULL(hs.owner, '(sin owner)')                                             AS owner,
  CONCAT(CAST(n.estado_mm_id AS STRING), ' · ', t.estado_txt)                 AS estado_mm,
  IFNULL(CAST(n.estado_inmo_id AS STRING), '(nunca calificó Inmo)')           AS estado_inmo
FROM negocios n
JOIN tig t            ON t.c = n.c AND t.nid = n.nid
LEFT JOIN cal_inmo ci ON ci.c = n.c AND ci.nid = n.nid
LEFT JOIN hs          ON hs.nid = n.nid
LEFT JOIN `sellers-main-prod.hubspot.deal_pipelines` p ON p.id = hs.pipeline_id
WHERE n.estado_mm_id IN (20, 63)   -- califica para MM
  AND ci.nid IS NULL               -- y nunca calificó para Inmo
ORDER BY n.c, t.fecha_creacion DESC, n.nid
