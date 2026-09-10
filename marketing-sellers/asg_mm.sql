-- Hoja "Asignación de leads" · tabla de ASIGNADOS MARKET MAKER (Colombia)
--
-- Tres filas MECE: el total se descompone en "directo por primera vez" + "venía de Inmo",
-- y esas dos suman exactamente el total. Cuarta fila de contraste con el mart del WBR.
--
-- FUENTE: `sellers-main-prod.hubspot.historical` con propiedad='pipeline'.
--   El `valor` es el pipeline_id. MM = 798578615 ("Sellers - Market Maker CO (NUEVO)")
--   INMO = 803674753 ("Nuevo - Inmobiliaria CO").
--   ⚠ NO usar `bi_co.seguimiento_asignacion_ibuyer_co.pipeline`: es SNAPSHOT del pipeline
--   actual del deal, así que da 0 casos de "pasó por MM primero". Verificado 2026-08-04.
--   ⚠ `historical` tiene ~5 h de rezago (batch): el período en curso siempre va corto.
--
-- POR QUÉ NO EL MART: `sellers_leads_asignados_marketing_wbr_mart` no tiene columna de
--   producto, y su filtro F2 se queda solo con la PRIMERA asignación cronológica del nid
--   sin importar el producto. Un lead asignado a Inmo y después a MM queda fuera → la fila
--   "venía de Inmo" sería 0 por construcción. Por eso las tres filas salen de `historical`
--   y el mart va como fila de contraste rotulada, no como cabeza de la descomposición.
--   Medido 2026-09-09: los dos universos difieren entre −12,5 % y +28 % por mes.
--
-- VENTANA: desde 2026-05-01. Antes está contaminado por cambios en la lógica de asignación
--   (los asignados MM caen de 39,6k en sep-2025 a ~8k en jun-2026 y el mix cambia en abril).
--
-- SOLO COLOMBIA en esta versión: los pipeline_id de arriba son de CO. El de MM en México
--   todavía no está identificado (INMO MX es 638550350). Cuando aparezca, se agrega otra
--   rama con c='México'.
--
-- Salida larga: {g, c, p, asg, directo, de_inmo, mart} — mismo shape que query.sql.

WITH
  pipe AS (
    SELECT nid, valor AS pipeline, MIN(fecha) AS primera
    FROM `sellers-main-prod.hubspot.historical`
    WHERE propiedad = 'pipeline'
      AND valor IN ('798578615', '803674753')
      AND nid IS NOT NULL
    GROUP BY nid, valor
  ),

  primera_por_producto AS (
    SELECT
      nid,
      MIN(IF(pipeline = '798578615', primera, NULL)) AS primera_mm,
      MIN(IF(pipeline = '803674753', primera, NULL)) AS primera_inmo
    FROM pipe
    GROUP BY nid
  ),

  -- Universo: nids cuya PRIMERA entrada al pipeline MM cae en la ventana.
  -- Un nid aparece una sola vez, en el período de su primera asignación a MM.
  base AS (
    SELECT
      nid,
      DATE(primera_mm) AS fecha,
      (primera_inmo IS NOT NULL AND primera_inmo < primera_mm) AS venia_inmo
    FROM primera_por_producto
    WHERE primera_mm IS NOT NULL
      AND DATE(primera_mm) >= DATE '2026-05-01'
  ),

  -- Fila de contraste: el mart oficial del WBR. Universo distinto (ver cabecera).
  mart AS (
    SELECT DISTINCT nid, dia AS fecha
    FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
    WHERE pais = 'colombia'
      AND dia >= DATE '2026-05-01'
  ),

  eventos AS (
    SELECT fecha, nid, 'hist' AS universo, venia_inmo FROM base
    UNION ALL
    SELECT fecha, nid, 'mart' AS universo, FALSE          FROM mart
  ),

  -- Períodos: los últimos 25 de cada granularidad, tomados del universo MM (no del mart),
  -- porque es el que manda las columnas de la tabla. Mismos cortes que query.sql:
  -- W = ISOWEEK (lun-dom) · C = WEEK(WEDNESDAY) = ciclo comercial (mié-mar).
  day_periods     AS (SELECT DISTINCT fecha                          p FROM base ORDER BY p DESC LIMIT 25),
  week_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, ISOWEEK)     p FROM base ORDER BY p DESC LIMIT 25),
  comm_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, WEEK(WEDNESDAY)) p FROM base ORDER BY p DESC LIMIT 25),
  month_periods   AS (SELECT DISTINCT DATE_TRUNC(fecha, MONTH)       p FROM base ORDER BY p DESC LIMIT 25),
  quarter_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, QUARTER)     p FROM base ORDER BY p DESC LIMIT 25),

  diario AS (
    SELECT 'D' g, 'Colombia' c, CAST(fecha AS STRING) p,
      COUNT(DISTINCT IF(universo = 'hist', nid, NULL))                       asg,
      COUNT(DISTINCT IF(universo = 'hist' AND NOT venia_inmo, nid, NULL))    directo,
      COUNT(DISTINCT IF(universo = 'hist' AND venia_inmo,     nid, NULL))    de_inmo,
      COUNT(DISTINCT IF(universo = 'mart', nid, NULL))                       mart
    FROM eventos WHERE fecha IN (SELECT p FROM day_periods) GROUP BY p
  ),
  semanal AS (
    SELECT 'W' g, 'Colombia' c, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING) p,
      COUNT(DISTINCT IF(universo = 'hist', nid, NULL))                       asg,
      COUNT(DISTINCT IF(universo = 'hist' AND NOT venia_inmo, nid, NULL))    directo,
      COUNT(DISTINCT IF(universo = 'hist' AND venia_inmo,     nid, NULL))    de_inmo,
      COUNT(DISTINCT IF(universo = 'mart', nid, NULL))                       mart
    FROM eventos WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY p
  ),
  ciclo AS (
    SELECT 'C' g, 'Colombia' c, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING) p,
      COUNT(DISTINCT IF(universo = 'hist', nid, NULL))                       asg,
      COUNT(DISTINCT IF(universo = 'hist' AND NOT venia_inmo, nid, NULL))    directo,
      COUNT(DISTINCT IF(universo = 'hist' AND venia_inmo,     nid, NULL))    de_inmo,
      COUNT(DISTINCT IF(universo = 'mart', nid, NULL))                       mart
    FROM eventos WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY p
  ),
  mensual AS (
    SELECT 'M' g, 'Colombia' c, FORMAT_DATE('%Y-%m', fecha) p,
      COUNT(DISTINCT IF(universo = 'hist', nid, NULL))                       asg,
      COUNT(DISTINCT IF(universo = 'hist' AND NOT venia_inmo, nid, NULL))    directo,
      COUNT(DISTINCT IF(universo = 'hist' AND venia_inmo,     nid, NULL))    de_inmo,
      COUNT(DISTINCT IF(universo = 'mart', nid, NULL))                       mart
    FROM eventos WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY p
  ),
  trimestral AS (
    SELECT 'Q' g, 'Colombia' c,
      CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)) p,
      COUNT(DISTINCT IF(universo = 'hist', nid, NULL))                       asg,
      COUNT(DISTINCT IF(universo = 'hist' AND NOT venia_inmo, nid, NULL))    directo,
      COUNT(DISTINCT IF(universo = 'hist' AND venia_inmo,     nid, NULL))    de_inmo,
      COUNT(DISTINCT IF(universo = 'mart', nid, NULL))                       mart
    FROM eventos WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY p
  ),
  anual AS (
    SELECT 'Y' g, 'Colombia' c, CAST(EXTRACT(YEAR FROM fecha) AS STRING) p,
      COUNT(DISTINCT IF(universo = 'hist', nid, NULL))                       asg,
      COUNT(DISTINCT IF(universo = 'hist' AND NOT venia_inmo, nid, NULL))    directo,
      COUNT(DISTINCT IF(universo = 'hist' AND venia_inmo,     nid, NULL))    de_inmo,
      COUNT(DISTINCT IF(universo = 'mart', nid, NULL))                       mart
    FROM eventos GROUP BY p
  )

SELECT * FROM diario
UNION ALL SELECT * FROM semanal
UNION ALL SELECT * FROM ciclo
UNION ALL SELECT * FROM mensual
UNION ALL SELECT * FROM trimestral
UNION ALL SELECT * FROM anual
ORDER BY g, p
