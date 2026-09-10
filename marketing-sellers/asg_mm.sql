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
-- VENTANA: toda la historia disponible, para dar los mismos 20 períodos que la tabla de
--   cosechas de la hoja de Calificación. Ojo al leerla: el mart llega a 2020-02, pero
--   `historical` solo a 2025-09-18 — antes de esa fecha las tres primeras filas van en "—",
--   no en cero. Y los meses previos a 2026-05 están contaminados por cambios en la lógica
--   de asignación (los asignados MM caen de 39,6k en sep-2025 a ~8k en jun-2026, y el mix
--   cambia en abril), así que sirven de contexto pero no para comparar contra hoy.
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
  ),

  -- CIFRA OFICIAL de MM. Alimenta la tabla de definiciones y la fila de contraste de esta.
  --
  -- SOLO SUMA ASIGNADOS QUE CALIFICAN PARA MARKET MAKER, y eso aplica a los dos países.
  -- No es un recorte técnico: para Marketing la prioridad sigue siendo optimizar por leads
  -- que califiquen para MM, así que un asignado que no calificaba nunca fue el objetivo.
  -- Lo consiguen cuatro de los 16 filtros del mart: estado del deal en la lista permitida
  -- (Sin pricing inicial / No gestionado / Cierre / No hay suficientes datos),
  -- check_a_pricing = 1, calificacion_del_lead_v2 <> N/NH, y asignacion_descartes_top IS
  -- NULL, que saca a los que solo fueron a inmobiliaria.
  --
  -- Validado 2026-09-09: abr-2026 = 5.080, exacto contra el WBR (977+1252+2309+542).
  mart AS (
    SELECT DISTINCT nid, dia AS fecha
    FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
    WHERE pais = 'colombia'
      -- Las 6 fuentes de marketing CO: WEB(3), Habimetro(7), CRM(20), Comercial(35),
      -- Brokers(39) y Leadforms(47/37/41/42 — cuatro ids en una sola etiqueta).
      -- Fuera de las 6 hay 0-2 leads/mes, pero el filtro va explícito porque ES la
      -- definición, no una limpieza de datos.
      AND fuente_id_tig IN (3, 7, 20, 35, 39, 47, 37, 41, 42)
  ),

  eventos AS (
    SELECT fecha, nid, 'hist' AS universo, venia_inmo FROM base
    UNION ALL
    SELECT fecha, nid, 'mart' AS universo, FALSE          FROM mart
  ),

  -- Períodos: los últimos 25 de cada granularidad sobre la UNIÓN de los dos universos,
  -- para que las columnas lleguen tan atrás como el mart y no se corten donde arranca
  -- `historical`. Mismos cortes que query.sql:
  -- W = ISOWEEK (lun-dom) · C = WEEK(WEDNESDAY) = ciclo comercial (mié-mar).
  day_periods     AS (SELECT DISTINCT fecha                          p FROM eventos ORDER BY p DESC LIMIT 25),
  week_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, ISOWEEK)     p FROM eventos ORDER BY p DESC LIMIT 25),
  comm_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, WEEK(WEDNESDAY)) p FROM eventos ORDER BY p DESC LIMIT 25),
  month_periods   AS (SELECT DISTINCT DATE_TRUNC(fecha, MONTH)       p FROM eventos ORDER BY p DESC LIMIT 25),
  quarter_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, QUARTER)     p FROM eventos ORDER BY p DESC LIMIT 25),

  diario AS (
    SELECT 'D' g, 'Colombia' c, CAST(fecha AS STRING) p,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist", nid, NULL)))                    asg,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND NOT venia_inmo, nid, NULL))) directo,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND venia_inmo, nid, NULL)))     de_inmo,
      IF(COUNTIF(universo="mart")=0, NULL, COUNT(DISTINCT IF(universo="mart", nid, NULL)))                    mart
    FROM eventos WHERE fecha IN (SELECT p FROM day_periods) GROUP BY p
  ),
  semanal AS (
    SELECT 'W' g, 'Colombia' c, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING) p,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist", nid, NULL)))                    asg,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND NOT venia_inmo, nid, NULL))) directo,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND venia_inmo, nid, NULL)))     de_inmo,
      IF(COUNTIF(universo="mart")=0, NULL, COUNT(DISTINCT IF(universo="mart", nid, NULL)))                    mart
    FROM eventos WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY p
  ),
  ciclo AS (
    SELECT 'C' g, 'Colombia' c, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING) p,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist", nid, NULL)))                    asg,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND NOT venia_inmo, nid, NULL))) directo,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND venia_inmo, nid, NULL)))     de_inmo,
      IF(COUNTIF(universo="mart")=0, NULL, COUNT(DISTINCT IF(universo="mart", nid, NULL)))                    mart
    FROM eventos WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY p
  ),
  mensual AS (
    SELECT 'M' g, 'Colombia' c, FORMAT_DATE('%Y-%m', fecha) p,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist", nid, NULL)))                    asg,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND NOT venia_inmo, nid, NULL))) directo,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND venia_inmo, nid, NULL)))     de_inmo,
      IF(COUNTIF(universo="mart")=0, NULL, COUNT(DISTINCT IF(universo="mart", nid, NULL)))                    mart
    FROM eventos WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY p
  ),
  trimestral AS (
    SELECT 'Q' g, 'Colombia' c,
      CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)) p,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist", nid, NULL)))                    asg,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND NOT venia_inmo, nid, NULL))) directo,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND venia_inmo, nid, NULL)))     de_inmo,
      IF(COUNTIF(universo="mart")=0, NULL, COUNT(DISTINCT IF(universo="mart", nid, NULL)))                    mart
    FROM eventos WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY p
  ),
  anual AS (
    SELECT 'Y' g, 'Colombia' c, CAST(EXTRACT(YEAR FROM fecha) AS STRING) p,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist", nid, NULL)))                    asg,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND NOT venia_inmo, nid, NULL))) directo,
      IF(COUNTIF(universo="hist")=0, NULL, COUNT(DISTINCT IF(universo="hist" AND venia_inmo, nid, NULL)))     de_inmo,
      IF(COUNTIF(universo="mart")=0, NULL, COUNT(DISTINCT IF(universo="mart", nid, NULL)))                    mart
    FROM eventos GROUP BY p
  )

SELECT * FROM diario
UNION ALL SELECT * FROM semanal
UNION ALL SELECT * FROM ciclo
UNION ALL SELECT * FROM mensual
UNION ALL SELECT * FROM trimestral
UNION ALL SELECT * FROM anual
ORDER BY g, p
