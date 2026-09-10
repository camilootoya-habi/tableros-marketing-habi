-- Hoja "Asignación de leads" · ASIGNADOS TOTALES y su reparto por producto (Colombia)
--
-- Universo: todo lead que (a) fue calificado para Market Maker o para Inmobiliaria, y
-- (b) se asignó a un `hubspot_owner_id`. Bucketeado por la fecha de su PRIMERA asignación.
--
-- Cuatro filas, las tres últimas MECE: suman exactamente el total.
--   asg        = asignados totales
--   solo_mm    = calificados exclusivamente para MM        (product_qualified='ibuyer')
--   solo_inmo  = calificados exclusivamente para Inmo      (product_qualified='real_estate')
--   ambos      = calificados para los dos productos        ('ibuyer_and_real_estate')
--
-- FUENTES
--   Asignación: `sellers-main-prod.hubspot.historical` con propiedad='hubspot_owner_id' y
--     `valor` no vacío. MIN(fecha) por nid = su primera asignación a un comercial. Es la
--     misma señal que usa el tablero `asignacion-co`. Volumen sano: 22-35k nids/mes.
--   Calificación: `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble`,
--     tomando el `product_qualified` más reciente por nid (ORDER BY fecha_creacion DESC).
--     Valores en CO: ibuyer_and_real_estate 31.172 · real_estate 10.101 · ibuyer 7.579 ·
--     transient 100.041 · vacío 3,6M. Los dos últimos NO son calificados y quedan fuera.
--
-- POR QUÉ NO SE RECONSTRUYE DESDE EL MART: el mart es una tabla materializada con sus 16
--   filtros ya aplicados, no se le puede quitar uno. Se intentó reconstruirlo desde
--   `tabla_inmuebles_general` y no cuadra (−1,8% a +4,2%): F15 solo se puede aproximar
--   porque `asignacion_descartes_top` no es accesible por IAM, los estados de la TIG son
--   valores actuales y no del momento de la asignación, y F4-F6 no son reproducibles.
--   Esta definición no intenta imitar al mart: parte de la calificación de producto, que
--   es el dato que de verdad responde la pregunta.
--
-- SIN FILTRO DE FUENTE, a propósito. Medido 2026-09-10: restringir a las 6 fuentes de
--   marketing da el MISMO número (7.059 vs 7.059 en julio; una sola diferencia de 1 lead
--   en junio). Como no cambia nada, se omite el join a la TIG — que es la tabla más grande
--   de las tres — y la query baja de ~50 GB a una fracción.
--
-- ⚠️ NO ES CITABLE en el WBR ni en el OKR: ahí se reporta el mart. Esta tabla dimensiona
--   la operación de asignación completa. Referencia de magnitud (jul-2026): 7.059 totales
--   contra 5.147 del mart oficial.
--
-- SOLO COLOMBIA por ahora: `co_rds_staging` y el pipeline de CO.
--
-- Salida larga: {g, c, p, asg, solo_mm, solo_inmo, ambos}.

WITH
  pq AS (
    SELECT
      CAST(nid AS STRING) AS nid,
      TRIM(ARRAY_AGG(product_qualified ORDER BY fecha_creacion DESC LIMIT 1)[OFFSET(0)]) AS pq
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble`
    WHERE nid IS NOT NULL
    GROUP BY nid
  ),

  owner AS (
    SELECT CAST(nid AS STRING) AS nid, MIN(DATE(fecha)) AS fecha
    FROM `sellers-main-prod.hubspot.historical`
    WHERE propiedad = 'hubspot_owner_id'
      AND valor IS NOT NULL AND TRIM(valor) <> ''
      AND nid IS NOT NULL
    GROUP BY nid
  ),

  base AS (
    SELECT o.nid, o.fecha, pq.pq
    FROM owner o
    JOIN pq USING (nid)
    WHERE pq.pq IN ('ibuyer', 'real_estate', 'ibuyer_and_real_estate')
  ),

  -- Mismos cortes que query.sql, asg_mm.sql y asg_inmo.sql:
  -- W = ISOWEEK (lun-dom) · C = WEEK(WEDNESDAY) = ciclo comercial (mié-mar).
  day_periods     AS (SELECT DISTINCT fecha                              p FROM base ORDER BY p DESC LIMIT 25),
  week_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, ISOWEEK)         p FROM base ORDER BY p DESC LIMIT 25),
  comm_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, WEEK(WEDNESDAY)) p FROM base ORDER BY p DESC LIMIT 25),
  month_periods   AS (SELECT DISTINCT DATE_TRUNC(fecha, MONTH)           p FROM base ORDER BY p DESC LIMIT 25),
  quarter_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, QUARTER)         p FROM base ORDER BY p DESC LIMIT 25),

  agg AS (
    SELECT 'D' g, CAST(fecha AS STRING) p,
      COUNT(DISTINCT nid)                                                    asg,
      COUNT(DISTINCT IF(pq = 'ibuyer', nid, NULL))                           solo_mm,
      COUNT(DISTINCT IF(pq = 'real_estate', nid, NULL))                      solo_inmo,
      COUNT(DISTINCT IF(pq = 'ibuyer_and_real_estate', nid, NULL))           ambos
    FROM base WHERE fecha IN (SELECT p FROM day_periods) GROUP BY p
    UNION ALL
    SELECT 'W', CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING),
      COUNT(DISTINCT nid),
      COUNT(DISTINCT IF(pq = 'ibuyer', nid, NULL)),
      COUNT(DISTINCT IF(pq = 'real_estate', nid, NULL)),
      COUNT(DISTINCT IF(pq = 'ibuyer_and_real_estate', nid, NULL))
    FROM base WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY 2
    UNION ALL
    SELECT 'C', CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING),
      COUNT(DISTINCT nid),
      COUNT(DISTINCT IF(pq = 'ibuyer', nid, NULL)),
      COUNT(DISTINCT IF(pq = 'real_estate', nid, NULL)),
      COUNT(DISTINCT IF(pq = 'ibuyer_and_real_estate', nid, NULL))
    FROM base WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY 2
    UNION ALL
    SELECT 'M', FORMAT_DATE('%Y-%m', fecha),
      COUNT(DISTINCT nid),
      COUNT(DISTINCT IF(pq = 'ibuyer', nid, NULL)),
      COUNT(DISTINCT IF(pq = 'real_estate', nid, NULL)),
      COUNT(DISTINCT IF(pq = 'ibuyer_and_real_estate', nid, NULL))
    FROM base WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY 2
    UNION ALL
    SELECT 'Q', CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q',
                       CAST(EXTRACT(QUARTER FROM fecha) AS STRING)),
      COUNT(DISTINCT nid),
      COUNT(DISTINCT IF(pq = 'ibuyer', nid, NULL)),
      COUNT(DISTINCT IF(pq = 'real_estate', nid, NULL)),
      COUNT(DISTINCT IF(pq = 'ibuyer_and_real_estate', nid, NULL))
    FROM base WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY 2
    UNION ALL
    SELECT 'Y', CAST(EXTRACT(YEAR FROM fecha) AS STRING),
      COUNT(DISTINCT nid),
      COUNT(DISTINCT IF(pq = 'ibuyer', nid, NULL)),
      COUNT(DISTINCT IF(pq = 'real_estate', nid, NULL)),
      COUNT(DISTINCT IF(pq = 'ibuyer_and_real_estate', nid, NULL))
    FROM base GROUP BY 2
  )

SELECT g, 'Colombia' AS c, p, asg, solo_mm, solo_inmo, ambos
FROM agg
ORDER BY g, p
