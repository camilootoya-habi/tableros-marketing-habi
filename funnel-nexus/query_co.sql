-- funnel-nexus/query_co.sql — CO
-- Universo: leads fuente WEB, sub-fuente Nexus (callcenter) en HubSpot.
-- Salida: una fila por nid con la fecha (nullable) de cada etapa del funnel.
--   d_reg           registro (TIG fecha_creacion)
--   d_calif_mm      1a calificación MM (estado_id IN 20,63)
--   d_calif_inmo    1a calificación INMO (state_id = 20)
--   d_asig          1a asignación (mart WBR oficial)
--   d_cierre_mm     Cierre - Comprado (funnel HubSpot MM)
--   d_captacion_inmo  Captación INMO (DWH canónico — pendiente acceso IAM, hoy NULL)
-- build.py agrega a grano diario en vistas cosecha/evento. Volumen chico a propósito.

WITH base AS (
  SELECT CAST(nid AS INT64) AS nid, MIN(createdate) AS created
  FROM `sellers-main-prod.hubspot.deals`
  WHERE fuente = 'WEB' AND sub_fuente = 'Nexus'
    AND country = 'Colombia' AND nid IS NOT NULL
  GROUP BY nid
),
reg AS (
  SELECT g.nid, ANY_VALUE(g.negocio_id) AS negocio_id, MIN(CAST(g.fecha_creacion AS DATE)) AS d_reg
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g
  JOIN base b ON g.nid = b.nid
  WHERE g.fecha_creacion IS NOT NULL
  GROUP BY g.nid
),
mm AS (
  SELECT negocio_id, MIN(CAST(fecha_actualizacion AS DATE)) AS d
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
  WHERE estado_id IN (20, 63)
  GROUP BY negocio_id
),
inmo AS (
  SELECT deal_id AS negocio_id, MIN(CAST(date_create AS DATE)) AS d
  FROM `sellers-main-prod.co_rds_staging.habi_db_history_state_real_estate`
  WHERE state_id = 20
  GROUP BY deal_id
),
asig AS (
  SELECT nid, MIN(CAST(dia AS DATE)) AS d
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE pais = 'colombia'
  GROUP BY nid
),
cierre AS (
  SELECT nid, MIN(CAST(fecha AS DATE)) AS d
  FROM `papyrus-data.habi_wh_bi.funnel_diarios_col`
  WHERE valor = 'Cierre - Comprado' AND nid IS NOT NULL
  GROUP BY nid
),
nexus_agent AS (
  -- agente del portal Nexus que creó el lead: primer registro cuyo agente
  -- contiene 'nexus' (incluye 'nexus:correo@…' y cuentas de prueba 'prueba_nexus …')
  SELECT negocio_id, REGEXP_REPLACE(agente, r'^(?i)nexus:', '') AS agent
  FROM (
    SELECT negocio_id, agente,
      ROW_NUMBER() OVER (PARTITION BY negocio_id ORDER BY fecha_actualizacion) AS rn
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
    WHERE LOWER(agente) LIKE '%nexus%'
  )
  WHERE rn = 1
)
SELECT
  r.nid                          AS nid,
  na.agent                       AS nexus_agent,
  CAST(b.created AS STRING)      AS created,
  CAST(r.d_reg AS STRING)        AS d_reg,
  CAST(mm.d AS STRING)           AS d_calif_mm,
  CAST(inmo.d AS STRING)         AS d_calif_inmo,
  CAST(asig.d AS STRING)         AS d_asig,
  CAST(cierre.d AS STRING)       AS d_cierre_mm,
  CAST(NULL AS STRING)           AS d_captacion_inmo
FROM reg r
JOIN base b            ON b.nid           = r.nid
LEFT JOIN mm           ON mm.negocio_id   = r.negocio_id
LEFT JOIN inmo         ON inmo.negocio_id = r.negocio_id
LEFT JOIN asig         ON asig.nid        = r.nid
LEFT JOIN cierre       ON cierre.nid      = r.nid
LEFT JOIN nexus_agent  na ON na.negocio_id = r.negocio_id
