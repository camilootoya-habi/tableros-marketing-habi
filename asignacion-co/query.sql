-- Tablero asignación MM vs INMO (CO)
-- Grano de salida: filas largas {kind, lente, d, dim, dim_val, metrica, n}
--   + filas {kind='tiempo', gran, periodo, salto, mediana, p90, n}
-- El frontend bucketea las filas kind='count' a semana/mes/ciclo y toma los últimos 20 períodos.
-- Ventana: 760 días (20 períodos mensuales + colchón de maduración de 90 d).
-- Definiciones: docs/superpowers/specs/2026-08-04-tablero-asignacion-co-design.md

WITH leads AS (
  SELECT
    CAST(t.nid AS STRING)                        AS nid,
    DATE(t.fecha_creacion)                       AS d_creacion,
    t.fuente_id                                  AS fuente_id,
    COALESCE(NULLIF(TRIM(t.fuente), ''), '(sin fuente)')                AS fuente,
    COALESCE(NULLIF(TRIM(t.area_metropolitana), ''), '(sin área)')      AS area
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` t
  WHERE t.nid IS NOT NULL
    AND DATE(t.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 760 DAY)
    AND DATE(t.fecha_creacion) <  CURRENT_DATE()
)
, asig AS (
  SELECT
    CAST(nid AS STRING) AS nid,
    MIN(DATE(fecha_asignacion)) AS d_asig,
    COUNT(*) AS n_asig,
    ARRAY_AGG(STRUCT(
      LOWER(TRIM(tipo))                                   AS tipo,
      TRIM(tipo_asignacion)                               AS tipo_asignacion,
      COALESCE(NULLIF(TRIM(equipo_inicial), ''), '(sin equipo)') AS equipo
    ) ORDER BY fecha_asignacion LIMIT 1)[OFFSET(0)] AS a1,
    MIN(IF(LOWER(TRIM(tipo)) = 'gabi', DATE(fecha_asignacion), NULL)) AS d_gabi
  FROM `sellers-main-prod.bi_co.seguimiento_asignacion_ibuyer_co`
  WHERE fecha_asignacion IS NOT NULL
    AND DATE(fecha_asignacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 940 DAY)
  GROUP BY nid
)
, owner AS (
  SELECT CAST(nid AS STRING) AS nid, MIN(DATE(fecha)) AS d_owner
  FROM `sellers-main-prod.hubspot.historical`
  WHERE propiedad = 'hubspot_owner_id'
    AND valor IS NOT NULL AND TRIM(valor) <> ''
    AND DATE(fecha) >= DATE_SUB(CURRENT_DATE(), INTERVAL 940 DAY)
  GROUP BY nid
)
, pipe_ev AS (
  SELECT
    CAST(nid AS STRING) AS nid,
    TIMESTAMP(fecha) AS ts,
    IF(TRIM(valor) = '798578615', 'MM', 'INMO') AS prod
  FROM `sellers-main-prod.hubspot.historical`
  WHERE propiedad = 'pipeline'
    AND TRIM(valor) IN ('798578615', '803674753')
    AND DATE(fecha) >= DATE_SUB(CURRENT_DATE(), INTERVAL 940 DAY)
)
, pipes AS (
  SELECT
    nid,
    MIN(IF(prod = 'MM',   ts, NULL)) AS ts_mm,
    MIN(IF(prod = 'INMO', ts, NULL)) AS ts_inmo,
    MIN(ts)                          AS ts_prod_1,
    ARRAY_AGG(prod ORDER BY ts LIMIT 1)[OFFSET(0)] AS prod_1,
    DATE(MIN(IF(prod = 'MM',   ts, NULL))) AS d_mm,
    DATE(MIN(IF(prod = 'INMO', ts, NULL))) AS d_inmo,
    DATE(MIN(ts))                          AS d_prod_1,
    LOGICAL_OR(prod = 'INMO' AND ts > primera_mm)   AS inmo_despues_de_mm,
    LOGICAL_OR(prod = 'MM'   AND ts > primera_inmo) AS mm_despues_de_inmo
  FROM (
    SELECT nid, ts, prod,
           MIN(IF(prod = 'MM',   ts, NULL)) OVER (PARTITION BY nid) AS primera_mm,
           MIN(IF(prod = 'INMO', ts, NULL)) OVER (PARTITION BY nid) AS primera_inmo
    FROM pipe_ev
  )
  GROUP BY nid
)
, gabi AS (
  SELECT CAST(nid AS STRING) AS nid,
         ARRAY_AGG(product_qualified ORDER BY fecha_creacion DESC LIMIT 1)[OFFSET(0)] AS product_qualified
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble`
  WHERE nid IS NOT NULL
  GROUP BY nid
)
, wbr AS (
  SELECT DISTINCT CAST(nid AS STRING) AS nid
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE LOWER(pais) = 'colombia'
    AND dia >= DATE_SUB(CURRENT_DATE(), INTERVAL 940 DAY)
)
, base AS (
  SELECT
    l.nid, l.d_creacion, l.fuente_id, l.fuente, l.area,
    COALESCE(a.a1.equipo, '(sin equipo)')                   AS equipo,
    a.d_asig, a.n_asig,
    a.a1.tipo                                               AS tipo_1,
    a.a1.tipo_asignacion                                    AS tipo_asignacion_1,
    o.d_owner,
    LEAST(COALESCE(a.d_asig, DATE '9999-12-31'),
          COALESCE(o.d_owner, DATE '9999-12-31'))           AS d_primera_asig_raw,
    a.d_gabi,
    a.a1.tipo = 'gabi'                                      AS gabi_flag,
    COALESCE(NULLIF(TRIM(g.product_qualified), ''), '(sin calificar)') AS gabi_producto,
    p.prod_1, p.d_prod_1, p.d_mm, p.d_inmo,
    p.ts_mm, p.ts_inmo, p.ts_prod_1,
    p.inmo_despues_de_mm, p.mm_despues_de_inmo,
    w.nid IS NOT NULL                                       AS en_wbr
  FROM leads l
  LEFT JOIN asig  a USING (nid)
  LEFT JOIN owner o USING (nid)
  LEFT JOIN pipes p USING (nid)
  LEFT JOIN gabi  g USING (nid)
  LEFT JOIN wbr   w USING (nid)
)
, base2 AS (
  SELECT * EXCEPT (d_primera_asig_raw),
    IF(d_primera_asig_raw = DATE '9999-12-31', NULL, d_primera_asig_raw) AS d_primera_asig,
    CASE
      WHEN d_asig IS NULL AND d_owner IS NULL THEN NULL
      WHEN d_owner IS NULL THEN 'seguimiento'
      WHEN d_asig  IS NULL THEN 'owner'
      WHEN d_asig <= d_owner THEN 'seguimiento'
      ELSE 'owner'
    END AS senal_primera
  FROM base
)
, dims AS (
  SELECT nid, 'total'  AS dim, 'total' AS dim_val FROM base2
  UNION ALL SELECT nid, 'fuente', fuente FROM base2
  UNION ALL SELECT nid, 'area',   area   FROM base2
  UNION ALL SELECT nid, 'equipo', equipo FROM base2
)
, lente_a AS (
  SELECT
    b.d_creacion AS d, x.dim, x.dim_val,
    COUNT(DISTINCT b.nid) AS creados,
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL
                      AND DATE_DIFF(b.d_primera_asig, b.d_creacion, DAY) <= 30, b.nid, NULL)) AS asig_30d,
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL, b.nid, NULL))                             AS asig_ever,
    COUNT(DISTINCT IF(b.gabi_flag
                      AND DATE_DIFF(b.d_asig, b.d_creacion, DAY) <= 30, b.nid, NULL))         AS gabi_30d,
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL AND NOT COALESCE(b.gabi_flag, FALSE)
                      AND DATE_DIFF(b.d_primera_asig, b.d_creacion, DAY) <= 30, b.nid, NULL)) AS directo_30d,
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL AND b.prod_1 = 'MM'
                      AND DATE_DIFF(b.d_prod_1, b.d_creacion, DAY) <= 30, b.nid, NULL))       AS prod1_mm,
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL AND b.prod_1 = 'INMO'
                      AND DATE_DIFF(b.d_prod_1, b.d_creacion, DAY) <= 30, b.nid, NULL))       AS prod1_inmo,
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL AND b.prod_1 IS NULL
                      AND DATE_DIFF(b.d_primera_asig, b.d_creacion, DAY) <= 30, b.nid, NULL)) AS sin_producto
  FROM base2 b
  JOIN dims x USING (nid)
  GROUP BY d, dim, dim_val
)
SELECT 'count' AS kind, 'A' AS lente, d, dim, dim_val, metrica, n
FROM lente_a
UNPIVOT (n FOR metrica IN (
  creados, asig_30d, asig_ever, gabi_30d, directo_30d, prod1_mm, prod1_inmo, sin_producto
))
WHERE n > 0
