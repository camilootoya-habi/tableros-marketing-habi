-- ============================================================================
-- Leads que GABI todavía tiene sin liberar — México
-- ============================================================================
-- DEFINICIÓN DE "ATASCADO EN GABI" — las cinco condiciones, todas obligatorias:
--
--   1. Está en el indicador de asignados marketing del WBR
--      (`sellers_leads_asignados_marketing_wbr_mart`, pais='mexico').
--   2. GABI lo recibió: tiene al menos una fila con `tipo='gabi'` en
--      `bi_mx.seguimiento_asignacion_ibuyer`.
--   3. NO tiene fila de `tipo_asignacion_comercial='Primer Asignación comercial'`
--      con `flag_asignacion_comercial='aplica_asignacion'`.
--   4. Pasaron 6 días o más desde la fecha de asignación de marketing.
--   5. ⚠️ SIGUE EN MANOS DE GABI HOY: su `equipo_actual` es un equipo de GABI
--      (`gabi ibuyer` o `gabi inmobiliaria`).
--
-- La condición 5 es la que hay que tener presente. Sin ella el query devuelve 562
-- leads, pero 10 de esos ya están con un comercial real (inmobiliaria 1 y 2, inmo
-- ciudades, guadalajara): cambiaron de propietario en HubSpot sin que se creara la
-- fila de "Primer Asignación comercial", así que la condición 3 sola los marca
-- atascados cuando no lo están. Con la condición 5 quedan 552, de los cuales
-- 531 en `gabi ibuyer` (Market Maker) y 21 en `gabi inmobiliaria`.
--
-- Por qué 6 días: en abril, mayo y junio 2026 el 96,3%–98,5% de la cohorte ya
-- tenía comercial al día 6 y la curva se aplanaba ahí. Un lead que pasa el día 6
-- sin comercial históricamente ya no salía.
--
-- `hubspot_owner_id` guarda el EMAIL del propietario, no un id numérico. Se traen
-- dos vistas del mismo dato porque no siempre coinciden: `hubspot_owner_id` sale de
-- `hubspot.deals` (es lo que se ve al abrir el negocio en HubSpot) y
-- `propietario_actual_seguimiento` sale del seguimiento. `owner_coincide` marca si
-- las dos concuerdan.
--
-- Ventana: asignaciones de marketing desde 2026-07-01.
-- Para ver solo los de GABI Market Maker, descomentar el filtro del final.
-- ============================================================================
WITH liberados AS (            -- tienen primera asignación comercial: se excluyen
  SELECT DISTINCT nid
  FROM `sellers-main-prod.bi_mx.seguimiento_asignacion_ibuyer`
  WHERE tipo_asignacion_comercial = 'Primer Asignación comercial'
    AND flag_asignacion_comercial = 'aplica_asignacion'
),
mkt AS (                       -- asignados por marketing (indicador del WBR)
  SELECT CAST(nid AS INT64) AS nid, MIN(dia) AS f_mkt
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE LOWER(pais) = 'mexico' AND dia >= DATE '2026-07-01'
  GROUP BY 1
),
gabi AS (                      -- lo que GABI recibió, y su estado más reciente
  SELECT CAST(nid AS INT64) AS nid,
    MIN(fecha_asignacion) AS f_gabi,
    ARRAY_AGG(macro_etapa        ORDER BY fecha_asignacion DESC LIMIT 1)[SAFE_OFFSET(0)] AS macro_etapa,
    ARRAY_AGG(etapa              ORDER BY fecha_asignacion DESC LIMIT 1)[SAFE_OFFSET(0)] AS etapa,
    ARRAY_AGG(propietario_actual ORDER BY fecha_asignacion DESC LIMIT 1)[SAFE_OFFSET(0)] AS propietario_actual,
    ARRAY_AGG(equipo_actual      ORDER BY fecha_asignacion DESC LIMIT 1)[SAFE_OFFSET(0)] AS equipo_actual
  FROM `sellers-main-prod.bi_mx.seguimiento_asignacion_ibuyer`
  WHERE tipo = 'gabi'
  GROUP BY 1
),
lead AS (
  SELECT CAST(nid AS INT64) AS nid,
    ANY_VALUE(fuente) AS fuente, ANY_VALUE(area_metropolitana) AS area
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general`
  WHERE nid IS NOT NULL GROUP BY 1
),
deal AS (                      -- propietario del negocio en HubSpot (lo que se ve al abrir el registro)
  SELECT CAST(nid AS INT64) AS nid,
    ANY_VALUE(hubspot_owner_id) AS hubspot_owner_id
  FROM `sellers-main-prod.hubspot.deals`
  WHERE nid IS NOT NULL AND country = 'México'
  GROUP BY 1
),
pq AS (
  SELECT CAST(nid AS INT64) AS nid,
    ARRAY_AGG(COALESCE(NULLIF(TRIM(product_qualified),''),'sin_calificar')
              ORDER BY date_update DESC LIMIT 1)[OFFSET(0)] AS product_qualified
  FROM `sellers-main-prod.mx_rds_staging.habi_db_property_deal`
  WHERE nid IS NOT NULL GROUP BY 1
)
SELECT
  m.nid,
  m.f_mkt                                          AS fecha_asignacion_marketing,
  DATE_DIFF(CURRENT_DATE(), m.f_mkt, DAY)          AS dias_sin_liberar,
  DATE(g.f_gabi)                                   AS fecha_entrada_gabi,
  LOWER(TRIM(g.equipo_actual))                     AS gabi_que_lo_tiene,
  d.hubspot_owner_id                               AS hubspot_owner_id,
  g.propietario_actual                             AS propietario_actual_seguimiento,
  d.hubspot_owner_id = g.propietario_actual        AS owner_coincide,
  g.macro_etapa,
  g.etapa,
  IFNULL(pq.product_qualified, 'sin_dato')         AS product_qualified,
  l.fuente,
  l.area
FROM mkt m
JOIN gabi g            ON g.nid  = m.nid              -- (2) GABI lo recibió
LEFT JOIN liberados x  ON x.nid  = m.nid
LEFT JOIN lead l       ON l.nid  = m.nid
LEFT JOIN deal d       ON d.nid  = m.nid
LEFT JOIN pq           ON pq.nid = m.nid
WHERE x.nid IS NULL                                   -- (3) sin primera asignación comercial
  AND DATE_DIFF(CURRENT_DATE(), m.f_mkt, DAY) >= 6    -- (4) pasó el parámetro
  AND LOWER(TRIM(g.equipo_actual)) LIKE 'gabi%'       -- (5) SIGUE en manos de GABI hoy
  -- AND LOWER(TRIM(g.equipo_actual)) = 'gabi ibuyer'
ORDER BY dias_sin_liberar DESC, m.nid
