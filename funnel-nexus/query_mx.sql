-- funnel-nexus/query_mx.sql — MX
-- Universo: leads fuente WEB, sub-fuente Nexus (callcenter) en HubSpot.
-- Misma salida que query_co.sql (una fila por nid con fecha nullable por etapa).
-- Diferencias MX: TIG id_negocio, history por deal_id/state_id/date_create,
-- cierre en bi_mx.seguimiento_funnel_mex, mart pais='mexico'.

WITH base AS (
  SELECT CAST(nid AS INT64) AS nid, MIN(createdate) AS created
  FROM `sellers-main-prod.hubspot.deals`
  WHERE fuente = 'WEB' AND sub_fuente = 'Nexus'
    AND country = 'México' AND nid IS NOT NULL
  GROUP BY nid
),
reg AS (
  SELECT g.nid, ANY_VALUE(g.id_negocio) AS negocio_id, MIN(CAST(g.fecha_creacion AS DATE)) AS d_reg
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
  JOIN base b ON g.nid = b.nid
  WHERE g.fecha_creacion IS NOT NULL
  GROUP BY g.nid
),
mm AS (
  SELECT deal_id AS negocio_id, MIN(CAST(date_create AS DATE)) AS d
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
  WHERE state_id IN (20, 63)
  GROUP BY deal_id
),
inmo AS (
  SELECT deal_id AS negocio_id, MIN(CAST(date_create AS DATE)) AS d
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state_real_estate`
  WHERE state_id = 20
  GROUP BY deal_id
),
asig AS (
  SELECT nid, MIN(CAST(dia AS DATE)) AS d
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE pais = 'mexico'
  GROUP BY nid
),
cierre AS (
  SELECT nid, MIN(CAST(fecha AS DATE)) AS d
  FROM `sellers-main-prod.bi_mx.seguimiento_funnel_mex`
  WHERE valor = 'Cierre - Comprado' AND nid IS NOT NULL
  GROUP BY nid
),
nexus_agent AS (
  -- agente del portal Nexus que creó el lead: primer registro cuyo agent
  -- contiene 'nexus' (incluye 'nexus:correo@…' y cuentas de prueba 'prueba_nexus …')
  SELECT negocio_id, REGEXP_REPLACE(agent, r'^(?i)nexus:', '') AS agent
  FROM (
    SELECT deal_id AS negocio_id, agent,
      ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY date_create) AS rn
    FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
    WHERE LOWER(agent) LIKE '%nexus%'
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
