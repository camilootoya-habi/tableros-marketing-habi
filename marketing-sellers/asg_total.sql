-- Hoja "Asignación de leads" · ASIGNADOS TOTALES y su reparto por producto (Colombia)
--
-- Universo: todo lead que (a) fue calificado para Market Maker o para Inmobiliaria, y
-- (b) se asignó a un `hubspot_owner_id`. Bucketeado por la fecha de su PRIMERA asignación.
--
-- Cuatro filas, las tres últimas MECE: suman exactamente el total.
--   asg        = asignados totales
--   solo_mm    = calificado para MM y nunca para Inmo
--   solo_inmo  = calificado para Inmo y nunca para MM
--   ambos      = calificado para los dos productos
--
-- ── CALIFICACIÓN: por PASO POR ESTADO, no por `product_qualified` ────────────────
--   MM   → pasó por `estado_id IN (20, 63)` en
--          `co_rds_staging.habi_db_tabla_historico_estado_v2` (por `negocio_id`)
--   INMO → pasó por `state_id = 20` en
--          `co_rds_staging.habi_db_history_state_real_estate` (por `deal_id`)
--   Son las mismas fuentes e ids que usa `query.sql` de este tablero para "Calificados MM"
--   y "Calificados Inmo", así que las dos hojas hablan el mismo idioma.
--
--   Se prefiere sobre `product_qualified` por tres razones, medidas 2026-09-10:
--     1. Es un evento ("pasó por"), no el snapshot del último valor.
--     2. Es un SUPERCONJUNTO estricto: la definición ampliada (estados OR
--        product_qualified) da exactamente lo mismo que estados solos en los 16 meses
--        revisados. Todo lead con `product_qualified` pasó por esos estados.
--     3. Recoge algo más: jul 7.104 vs 7.059 · ago 7.558 vs 7.509 · may 7.145 vs 7.069.
--
-- ── ⚠️ VENTANA: DESDE 2026-03. NO ES UNA DECISIÓN, ES EL LÍMITE DEL DATO ─────────
--   `habi_db_history_state_real_estate` tiene **CERO filas antes de 2026-03**; su primer
--   registro es de ese mes. Sin esa tabla no existe la mitad "Inmo" de la definición, así
--   que un total de "calificado para MM o Inmo" no se puede calcular hacia atrás: daría
--   solo la parte de MM, que es otra cosa y se leería como una caída del indicador.
--
--   Cambiar de `product_qualified` a estados NO mueve este límite: `product_qualified`
--   también arranca en marzo-2026 (feb 678 → mar 4.610 de ~15.800 asignados/mes). Los dos
--   sistemas empezaron a registrar calificación de producto al mismo tiempo.
--
--   Por eso los períodos anteriores a 2026-03 salen en NULL → "—" en el tablero, en las
--   cuatro filas. Si algún día hace falta una serie más larga, tendría que ser un
--   indicador distinto y rotulado como tal: "calificados MM" solo, que sí llega a 2025-06.
--
-- ⚠️ NO ES CITABLE en el WBR ni en el OKR: ahí se reporta el mart. Esta tabla dimensiona
--   la operación de asignación completa. Referencia (jul-2026): 7.104 contra 5.147.
--
-- SIN FILTRO DE FUENTE, a propósito: restringir a las 6 fuentes de marketing daba el mismo
--   número, así que se omite el join a `tabla_inmuebles_general` — la tabla más grande — y
--   la query no paga ese escaneo.
--
-- SOLO COLOMBIA por ahora: todo sale de `co_rds_staging`.
--
-- Salida larga: {g, c, p, asg, solo_mm, solo_inmo, ambos}.

WITH
  negocios AS (
    SELECT CAST(nid AS STRING) AS nid, id AS biz_id
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble`
    WHERE nid IS NOT NULL
  ),

  cal_mm AS (
    SELECT DISTINCT n.nid
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2` h
    JOIN negocios n ON n.biz_id = h.negocio_id
    WHERE h.estado_id IN (20, 63)
  ),

  cal_inmo AS (
    SELECT DISTINCT n.nid
    FROM `sellers-main-prod.co_rds_staging.habi_db_history_state_real_estate` h
    JOIN negocios n ON n.biz_id = h.deal_id
    WHERE h.state_id = 20
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
    SELECT
      o.nid,
      o.fecha,
      mm.nid IS NOT NULL   AS es_mm,
      inmo.nid IS NOT NULL AS es_inmo
    FROM owner o
    LEFT JOIN cal_mm   mm   ON mm.nid   = o.nid
    LEFT JOIN cal_inmo inmo ON inmo.nid = o.nid
    WHERE (mm.nid IS NOT NULL OR inmo.nid IS NOT NULL)
      -- Límite del dato, no de la decisión. Ver la cabecera.
      AND o.fecha >= DATE '2026-03-01'
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
      COUNT(DISTINCT nid)                                              asg,
      COUNT(DISTINCT IF(es_mm AND NOT es_inmo, nid, NULL))             solo_mm,
      COUNT(DISTINCT IF(es_inmo AND NOT es_mm, nid, NULL))             solo_inmo,
      COUNT(DISTINCT IF(es_mm AND es_inmo, nid, NULL))                 ambos
    FROM base WHERE fecha IN (SELECT p FROM day_periods) GROUP BY p
    UNION ALL
    SELECT 'W', CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING),
      COUNT(DISTINCT nid),
      COUNT(DISTINCT IF(es_mm AND NOT es_inmo, nid, NULL)),
      COUNT(DISTINCT IF(es_inmo AND NOT es_mm, nid, NULL)),
      COUNT(DISTINCT IF(es_mm AND es_inmo, nid, NULL))
    FROM base WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY 2
    UNION ALL
    SELECT 'C', CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING),
      COUNT(DISTINCT nid),
      COUNT(DISTINCT IF(es_mm AND NOT es_inmo, nid, NULL)),
      COUNT(DISTINCT IF(es_inmo AND NOT es_mm, nid, NULL)),
      COUNT(DISTINCT IF(es_mm AND es_inmo, nid, NULL))
    FROM base WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY 2
    UNION ALL
    SELECT 'M', FORMAT_DATE('%Y-%m', fecha),
      COUNT(DISTINCT nid),
      COUNT(DISTINCT IF(es_mm AND NOT es_inmo, nid, NULL)),
      COUNT(DISTINCT IF(es_inmo AND NOT es_mm, nid, NULL)),
      COUNT(DISTINCT IF(es_mm AND es_inmo, nid, NULL))
    FROM base WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY 2
    UNION ALL
    SELECT 'Q', CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q',
                       CAST(EXTRACT(QUARTER FROM fecha) AS STRING)),
      COUNT(DISTINCT nid),
      COUNT(DISTINCT IF(es_mm AND NOT es_inmo, nid, NULL)),
      COUNT(DISTINCT IF(es_inmo AND NOT es_mm, nid, NULL)),
      COUNT(DISTINCT IF(es_mm AND es_inmo, nid, NULL))
    FROM base WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY 2
    UNION ALL
    SELECT 'Y', CAST(EXTRACT(YEAR FROM fecha) AS STRING),
      COUNT(DISTINCT nid),
      COUNT(DISTINCT IF(es_mm AND NOT es_inmo, nid, NULL)),
      COUNT(DISTINCT IF(es_inmo AND NOT es_mm, nid, NULL)),
      COUNT(DISTINCT IF(es_mm AND es_inmo, nid, NULL))
    FROM base GROUP BY 2
  )

SELECT g, 'Colombia' AS c, p, asg, solo_mm, solo_inmo, ambos
FROM agg
ORDER BY g, p
