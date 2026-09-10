-- Hoja "Asignación de leads" · ASIGNADOS INMOBILIARIA (Colombia)
--
-- Sirve a dos tablas del tablero:
--   1. la cifra OFICIAL del WBR ("Leads asignados equipo inmobiliaria"), y
--   2. su descomposición por historia previa en Market Maker.
--
-- FUENTE: `sellers-main-prod.bi_co.tablero_asignacion_inmo_col`, por
--   `fecha_primera_asignacion`, con `prioridad_de_gestion_inmo IN ('A','B')`.
--
-- ⚠️ EL FILTRO DE PRIORIDAD ES LA DEFINICIÓN, NO UN FILTRO DE CONVENIENCIA.
--   La cifra del WBR es la suma de las barras A + B, no el total de la tabla. Sin el
--   filtro sobra ~11%: en la ventana 20-jul a 30-ago hay 693 filas con prioridad NULL
--   y 6 con 'Descartado Gabi'. Validado semana a semana contra el WBR (2026-09-09):
--     20-jul  A+B del WBR = 174+722 = 896   · esta query = 901
--     10-ago  A+B del WBR = 187+787 = 974   · esta query = 984
--     17-ago  A+B del WBR = 142+671 = 813   · esta query = 831
--   Las diferencias de 5-20 leads y el drift de las semanas recientes vienen de que
--   `prioridad_de_gestion_inmo` es SNAPSHOT: se reescribe en cada refresh, así que la
--   serie histórica del split A/B se mueve sola. Nunca leer tendencia de la prioridad.
--
-- RUTA MM → INMO: se cruza con `sellers-main-prod.hubspot.historical` con
--   propiedad='pipeline' y valor='798578615' (pipeline MM CO), tomando MIN(fecha) como
--   su primera entrada a MM.
--   ⚠️ NO usar `bi_co.seguimiento_asignacion_ibuyer_co.pipeline`: es snapshot del
--   pipeline actual, da 0 casos de "MM primero".
--   ⚠️ `historical` tiene ~5 h de rezago: el período en curso va corto.
--
-- `directo` = sin entrada a MM ANTERIOR a su asignación a Inmo (incluye a los que
--   entraron a MM después). Con `de_mm` es MECE: suman exactamente el total.
--   Reproduce la línea punteada del WBR "Asignado directo a Inmo (sin pasar por MM)":
--     WBR 481 · 529 · 530 · 485 · 458   |   esta query 482 · 525 · 528 · 482 · 455
--   Ojo: en MX esa misma etiqueta mide otra cosa ("calificado para real_estate", ver
--   [[asignados_inmo_wbr_oficial]]). En CO la etiqueta sí describe lo que mide.
--
-- SOLO COLOMBIA: la tabla es `bi_co`. El equivalente MX es
--   `data_sellers_bo.leads_asignados_imobiliaria`, con otra definición y otros gotchas.
--
-- Salida larga: {g, c, p, asg, directo, de_mm} — mismo shape que asg_mm.sql.

WITH
  inmo AS (
    SELECT nid, fecha_primera_asignacion AS fecha
    FROM `sellers-main-prod.bi_co.tablero_asignacion_inmo_col`
    WHERE prioridad_de_gestion_inmo IN ('A', 'B')
      AND fecha_primera_asignacion >= DATE '2026-05-01'
  ),

  mm AS (
    SELECT nid, MIN(fecha) AS primera_mm
    FROM `sellers-main-prod.hubspot.historical`
    WHERE propiedad = 'pipeline'
      AND valor = '798578615'
      AND nid IS NOT NULL
    GROUP BY nid
  ),

  base AS (
    SELECT
      i.nid,
      i.fecha,
      (m.primera_mm IS NOT NULL AND DATE(m.primera_mm) <= i.fecha) AS venia_mm
    FROM inmo i
    LEFT JOIN mm m USING (nid)
  ),

  -- Mismos cortes que query.sql y asg_mm.sql:
  -- W = ISOWEEK (lun-dom) · C = WEEK(WEDNESDAY) = ciclo comercial (mié-mar).
  day_periods     AS (SELECT DISTINCT fecha                              p FROM base ORDER BY p DESC LIMIT 25),
  week_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, ISOWEEK)         p FROM base ORDER BY p DESC LIMIT 25),
  comm_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, WEEK(WEDNESDAY)) p FROM base ORDER BY p DESC LIMIT 25),
  month_periods   AS (SELECT DISTINCT DATE_TRUNC(fecha, MONTH)           p FROM base ORDER BY p DESC LIMIT 25),
  quarter_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, QUARTER)         p FROM base ORDER BY p DESC LIMIT 25),

  diario AS (
    SELECT 'D' g, 'Colombia' c, CAST(fecha AS STRING) p,
      COUNT(DISTINCT nid)                              asg,
      COUNT(DISTINCT IF(NOT venia_mm, nid, NULL))      directo,
      COUNT(DISTINCT IF(venia_mm,     nid, NULL))      de_mm
    FROM base WHERE fecha IN (SELECT p FROM day_periods) GROUP BY p
  ),
  semanal AS (
    SELECT 'W' g, 'Colombia' c, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING) p,
      COUNT(DISTINCT nid)                              asg,
      COUNT(DISTINCT IF(NOT venia_mm, nid, NULL))      directo,
      COUNT(DISTINCT IF(venia_mm,     nid, NULL))      de_mm
    FROM base WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY p
  ),
  ciclo AS (
    SELECT 'C' g, 'Colombia' c, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING) p,
      COUNT(DISTINCT nid)                              asg,
      COUNT(DISTINCT IF(NOT venia_mm, nid, NULL))      directo,
      COUNT(DISTINCT IF(venia_mm,     nid, NULL))      de_mm
    FROM base WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY p
  ),
  mensual AS (
    SELECT 'M' g, 'Colombia' c, FORMAT_DATE('%Y-%m', fecha) p,
      COUNT(DISTINCT nid)                              asg,
      COUNT(DISTINCT IF(NOT venia_mm, nid, NULL))      directo,
      COUNT(DISTINCT IF(venia_mm,     nid, NULL))      de_mm
    FROM base WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY p
  ),
  trimestral AS (
    SELECT 'Q' g, 'Colombia' c,
      CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)) p,
      COUNT(DISTINCT nid)                              asg,
      COUNT(DISTINCT IF(NOT venia_mm, nid, NULL))      directo,
      COUNT(DISTINCT IF(venia_mm,     nid, NULL))      de_mm
    FROM base WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY p
  ),
  anual AS (
    SELECT 'Y' g, 'Colombia' c, CAST(EXTRACT(YEAR FROM fecha) AS STRING) p,
      COUNT(DISTINCT nid)                              asg,
      COUNT(DISTINCT IF(NOT venia_mm, nid, NULL))      directo,
      COUNT(DISTINCT IF(venia_mm,     nid, NULL))      de_mm
    FROM base GROUP BY p
  )

SELECT * FROM diario
UNION ALL SELECT * FROM semanal
UNION ALL SELECT * FROM ciclo
UNION ALL SELECT * FROM mensual
UNION ALL SELECT * FROM trimestral
UNION ALL SELECT * FROM anual
ORDER BY g, p
