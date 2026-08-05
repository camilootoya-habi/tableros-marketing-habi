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
-- Rutas de llegada a INMO. El CASE es EXCLUYENTE y el orden importa:
--   1) regreso   : ya había estado en INMO, pasó por MM y volvió
--   2) gabi_mm   : GABI lo tomó y su calificación actual es de MM (ibuyer*), y pasó por MM antes de INMO
--   3) cruce     : pasó por MM antes de INMO (resto, incluye GABI con real_estate/transient/sin calificar)
--   4) gabi_prod : GABI lo tomó y NO pasó por MM antes
--   5) directo   : ni GABI ni MM previo
, rutas_inmo AS (
  SELECT b.*, CASE
    WHEN b.d_inmo IS NULL THEN NULL
    WHEN b.prod_1 = 'INMO' AND b.ts_mm IS NOT NULL AND b.ts_mm > b.ts_inmo
         AND b.inmo_despues_de_mm                                   THEN 'r_regreso'
    WHEN b.ts_mm IS NOT NULL AND b.ts_mm < b.ts_inmo
         AND COALESCE(b.gabi_flag, FALSE)
         AND b.gabi_producto IN ('ibuyer', 'ibuyer_and_real_estate') THEN 'r_gabi_mm_cruce'
    WHEN b.ts_mm IS NOT NULL AND b.ts_mm < b.ts_inmo                    THEN 'r_cruce'
    WHEN COALESCE(b.gabi_flag, FALSE)                                THEN 'r_gabi_prod'
    ELSE 'r_directo' END AS ruta
  FROM base2 b
)
-- Rutas de llegada a MM: espejo exacto, cambiando INMO <-> MM y la calificación de GABI
, rutas_mm AS (
  SELECT b.*, CASE
    WHEN b.d_mm IS NULL THEN NULL
    WHEN b.prod_1 = 'MM' AND b.mm_despues_de_inmo                    THEN 'r_regreso'
    WHEN b.ts_inmo IS NOT NULL AND b.ts_inmo < b.ts_mm
         AND COALESCE(b.gabi_flag, FALSE)
         AND b.gabi_producto IN ('real_estate', 'ibuyer_and_real_estate') THEN 'r_gabi_mm_cruce'
    WHEN b.ts_inmo IS NOT NULL AND b.ts_inmo < b.ts_mm                  THEN 'r_cruce'
    WHEN COALESCE(b.gabi_flag, FALSE)                                THEN 'r_gabi_prod'
    ELSE 'r_directo' END AS ruta
  FROM base2 b
)
, rutas_inmo_agg AS (
  SELECT d_inmo AS d, x.dim, x.dim_val,
         COUNT(DISTINCT r.nid) AS llegadas,
         COUNT(DISTINCT IF(ruta='r_directo',       r.nid, NULL)) AS r_directo,
         COUNT(DISTINCT IF(ruta='r_gabi_prod',     r.nid, NULL)) AS r_gabi_prod,
         COUNT(DISTINCT IF(ruta='r_gabi_mm_cruce', r.nid, NULL)) AS r_gabi_mm_cruce,
         COUNT(DISTINCT IF(ruta='r_cruce',         r.nid, NULL)) AS r_cruce,
         COUNT(DISTINCT IF(ruta='r_regreso',       r.nid, NULL)) AS r_regreso
  FROM rutas_inmo r
  JOIN dims x USING (nid)
  WHERE r.d_inmo IS NOT NULL
  GROUP BY d, x.dim, x.dim_val
)
, rutas_mm_agg AS (
  SELECT d_mm AS d, x.dim, x.dim_val,
         COUNT(DISTINCT r.nid) AS llegadas,
         COUNT(DISTINCT IF(ruta='r_directo',       r.nid, NULL)) AS r_directo,
         COUNT(DISTINCT IF(ruta='r_gabi_prod',     r.nid, NULL)) AS r_gabi_prod,
         COUNT(DISTINCT IF(ruta='r_gabi_mm_cruce', r.nid, NULL)) AS r_gabi_mm_cruce,
         COUNT(DISTINCT IF(ruta='r_cruce',         r.nid, NULL)) AS r_cruce,
         COUNT(DISTINCT IF(ruta='r_regreso',       r.nid, NULL)) AS r_regreso
  FROM rutas_mm r
  JOIN dims x USING (nid)
  WHERE r.d_mm IS NOT NULL
  GROUP BY d, x.dim, x.dim_val
)
SELECT 'count' AS kind, 'A' AS lente, CAST(d AS STRING) AS d, dim, dim_val, metrica, CAST(n AS STRING) AS n
FROM lente_a
UNPIVOT (n FOR metrica IN (
  creados, asig_30d, asig_ever, gabi_30d, directo_30d, prod1_mm, prod1_inmo, sin_producto
))
WHERE n > 0
UNION ALL
SELECT 'count', 'B', CAST(d AS STRING), dim, dim_val, metrica, CAST(n AS STRING)
FROM rutas_inmo_agg
UNPIVOT (n FOR metrica IN (llegadas, r_directo, r_gabi_prod, r_gabi_mm_cruce, r_cruce, r_regreso))
WHERE n > 0
UNION ALL
SELECT 'count', 'C', CAST(d AS STRING), dim, dim_val, metrica, CAST(n AS STRING)
FROM rutas_mm_agg
UNPIVOT (n FOR metrica IN (llegadas, r_directo, r_gabi_prod, r_gabi_mm_cruce, r_cruce, r_regreso))
WHERE n > 0
UNION ALL
-- Tiempos por salto (mediana/p90/n_casos pre-agregados; NO re-agregables desde grano diario).
-- Contrato: lente='TIEMPO' (familia), d=periodo (fecha real, ya truncado a su granularidad),
-- dim=granularidad (semana|mes|ciclo), dim_val=salto, metrica in (mediana|p90|n_casos), n=valor.
-- Una fila por medida (no empaquetado posicional) para que ningún nombre de columna mienta.
SELECT 'tiempo' AS kind, 'TIEMPO' AS lente, CAST(periodo AS STRING) AS d, gran AS dim,
       salto AS dim_val, metrica, CAST(valor AS STRING) AS n
FROM (
  SELECT gran, periodo, salto, mediana, p90, n
  FROM (
    SELECT gran, periodo, salto,
           APPROX_QUANTILES(dias, 100)[OFFSET(50)] AS mediana,
           APPROX_QUANTILES(dias, 100)[OFFSET(90)] AS p90,
           COUNT(*) AS n
    FROM (
      SELECT gran,
             CASE gran
               WHEN 'semana' THEN DATE_TRUNC(s.d_ancla, ISOWEEK)
               WHEN 'mes'    THEN DATE_TRUNC(s.d_ancla, MONTH)
               ELSE               DATE_TRUNC(s.d_ancla, WEEK(WEDNESDAY))
             END AS periodo,
             s.salto, s.dias
      FROM (
        SELECT 'creacion_gabi' AS salto, d_gabi AS d_ancla, DATE_DIFF(d_gabi, d_creacion, DAY) AS dias
          FROM base2 WHERE d_gabi IS NOT NULL
        UNION ALL
        SELECT 'gabi_mm',       d_mm,   DATE_DIFF(d_mm,   d_gabi, DAY)
          FROM base2 WHERE d_gabi IS NOT NULL AND d_mm   IS NOT NULL AND d_mm   >= d_gabi
        UNION ALL
        SELECT 'mm_inmo',       d_inmo, DATE_DIFF(d_inmo, d_mm,   DAY)
          FROM base2 WHERE d_mm   IS NOT NULL AND d_inmo IS NOT NULL AND d_inmo >  d_mm
        UNION ALL
        SELECT 'inmo_mm',       d_mm,   DATE_DIFF(d_mm,   d_inmo, DAY)
          FROM base2 WHERE d_inmo IS NOT NULL AND d_mm   IS NOT NULL AND d_mm   >  d_inmo
      ) s
      CROSS JOIN UNNEST(['semana','mes','ciclo']) AS gran
    )
    GROUP BY gran, periodo, salto
  )
)
UNPIVOT (valor FOR metrica IN (mediana AS 'mediana', p90 AS 'p90', n AS 'n_casos'))
UNION ALL
-- Reconciliación con el WBR mart: 4 cuadrantes + descomposición del gap "asignado y no en mart"
SELECT 'count', 'REC', CAST(d_creacion AS STRING), 'total', 'total', metrica, CAST(n AS STRING)
FROM (
  SELECT d_creacion,
    COUNT(DISTINCT IF(    asignado AND     en_wbr, nid, NULL)) AS q_asig_en_mart,
    COUNT(DISTINCT IF(    asignado AND NOT en_wbr, nid, NULL)) AS q_asig_no_mart,
    COUNT(DISTINCT IF(NOT asignado AND     en_wbr, nid, NULL)) AS q_noasig_en_mart,
    COUNT(DISTINCT IF(NOT asignado AND NOT en_wbr, nid, NULL)) AS q_noasig_no_mart,
    -- descomposición del cuadrante ⚠ "asignado y NO en el mart", por prioridad
    -- ⚠️ COALESCE obligatorio: con fuente_id NULL las tres condiciones evalúan a NULL (no a FALSE)
    -- y el lead se cae de los tres buckets, rompiendo la exhaustividad. Verificado: 41 leads así.
    -- Un fuente_id nulo no es fuente de marketing → cae en gap_no_marketing.
    COUNT(DISTINCT IF(asignado AND NOT en_wbr AND COALESCE(fuente_id, -1) = 1,  nid, NULL)) AS gap_ventanas,
    COUNT(DISTINCT IF(asignado AND NOT en_wbr AND COALESCE(fuente_id, -1) <> 1
                      AND COALESCE(fuente_id, -1) NOT IN (3,47,37,41,42,7,20,39,35), nid, NULL)) AS gap_no_marketing,
    COUNT(DISTINCT IF(asignado AND NOT en_wbr
                      AND COALESCE(fuente_id, -1) IN (3,47,37,41,42,7,20,39,35),      nid, NULL)) AS gap_sin_explicar
  FROM (SELECT *, d_primera_asig IS NOT NULL AS asignado FROM base2)
  GROUP BY d_creacion
)
UNPIVOT (n FOR metrica IN (
  q_asig_en_mart, q_asig_no_mart, q_noasig_en_mart, q_noasig_no_mart,
  gap_ventanas, gap_no_marketing, gap_sin_explicar
))
WHERE n > 0
