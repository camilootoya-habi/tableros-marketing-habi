-- Hoja "Asignación de leads" · ASIGNADOS MARKET MAKER (Colombia y México)
--
-- Tres filas MECE: el total se descompone en "directo por primera vez" + "venía de Inmo",
-- y esas dos suman exactamente el total. La cuarta serie, `mart`, es la CIFRA OFICIAL y
-- alimenta la tabla de Definiciones oficiales.
--
-- ── FUENTE DE LA DESCOMPOSICIÓN ──────────────────────────────────────────────────
--   `sellers-main-prod.hubspot.historical` con propiedad='pipeline'. El `valor` es el
--   pipeline_id, y hay cuatro en juego (catálogo: `hubspot.deal_pipelines`):
--     MM CO   = 798578615  "Sellers - Market Maker CO (NUEVO)"   desde 2025-09
--     INMO CO = 803674753  "Nuevo - Inmobiliaria CO"             desde 2025-10
--     MM MX   = 731899270  "Sellers - Market Maker MX (NUEVO)"   desde 2025-05
--     INMO MX = 638550350  "Nuevo - Inmobiliaria MX"             desde 2024-10
--   ⚠ NO usar `bi_co.seguimiento_asignacion_ibuyer_co.pipeline`: es SNAPSHOT del pipeline
--   actual del deal, así que da 0 casos de "pasó por MM primero". Verificado 2026-08-04.
--   ⚠ `historical` tiene ~5 h de rezago (batch): el período en curso siempre va corto.
--
-- ── CIFRA OFICIAL (serie `mart`) ─────────────────────────────────────────────────
--   `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`.
--   SOLO SUMA ASIGNADOS QUE CALIFICAN PARA MARKET MAKER, en los dos países. No es un
--   recorte técnico: para Marketing la prioridad sigue siendo optimizar por leads que
--   califiquen para MM, así que un asignado que no calificaba nunca fue el objetivo.
--   Lo consiguen cuatro de los 16 filtros del mart: estado del deal en la lista permitida
--   (Sin pricing inicial / No gestionado / Cierre / No hay suficientes datos),
--   check_a_pricing = 1, calificacion_del_lead_v2 <> N/NH, y asignacion_descartes_top IS
--   NULL, que saca a los que solo fueron a inmobiliaria.
--   Validado 2026-09-09 (CO): abr-2026 = 5.080, exacto contra el WBR (977+1252+2309+542).
--
-- ── POR QUÉ LA DESCOMPOSICIÓN NO SALE DEL MART ───────────────────────────────────
--   El mart no tiene columna de producto, y su filtro F2 se queda solo con la PRIMERA
--   asignación cronológica del nid sin importar el producto. Un lead asignado a Inmo y
--   después a MM queda fuera → la fila "venía de Inmo" sería 0 por construcción.
--   Medido 2026-09-09: los dos universos difieren entre −12,5 % y +28 % por mes, así que
--   el total de esta tabla NO cuadra con la cifra oficial y no debe cuadrar.
--
-- ── VENTANA ──────────────────────────────────────────────────────────────────────
--   Toda la historia, para dar los mismos 20 períodos que la tabla de cosechas. El mart
--   llega a 2020-02 pero `historical` arranca en las fechas de arriba: antes de eso las
--   tres primeras filas van en "—" y no en cero. Y los meses previos a 2026-05 están
--   contaminados por cambios en la lógica de asignación (los asignados MM CO caen de
--   39,6k en sep-2025 a ~8k en jun-2026): sirven de contexto, no para comparar.
--
-- ── NOTA DE ESTRUCTURA ───────────────────────────────────────────────────────────
--   El resto del repo escribe un CTE por granularidad (6 bloques). Aquí se usa un UNNEST
--   que mapea cada fecha a sus 6 claves de período y se agrega una sola vez. Con dos
--   países serían 12 bloques casi idénticos, y cada copia es una oportunidad de que uno
--   quede desincronizado. Los cortes son los mismos que `query.sql`:
--   W = ISOWEEK (lun-dom) · C = WEEK(WEDNESDAY) = ciclo comercial (mié-mar).
--
-- Salida larga: {g, c, p, asg, directo, de_inmo, mart}.

WITH
  pipe AS (
    SELECT
      IF(valor IN ('798578615', '803674753'), 'Colombia', 'México') AS c,
      nid,
      IF(valor IN ('798578615', '731899270'), 'MM', 'INMO')         AS producto,
      MIN(fecha)                                                    AS primera
    FROM `sellers-main-prod.hubspot.historical`
    WHERE propiedad = 'pipeline'
      AND valor IN ('798578615', '803674753', '731899270', '638550350')
      AND nid IS NOT NULL
    GROUP BY c, nid, producto
  ),

  primera_por_producto AS (
    SELECT
      c, nid,
      MIN(IF(producto = 'MM',   primera, NULL)) AS primera_mm,
      MIN(IF(producto = 'INMO', primera, NULL)) AS primera_inmo
    FROM pipe
    GROUP BY c, nid
  ),

  -- Universo: nids cuya PRIMERA entrada al pipeline MM de su país cae en la ventana.
  -- Cada nid aparece una sola vez, en el período de esa primera asignación.
  base AS (
    SELECT
      c, nid,
      DATE(primera_mm) AS fecha,
      (primera_inmo IS NOT NULL AND primera_inmo < primera_mm) AS venia_inmo
    FROM primera_por_producto
    WHERE primera_mm IS NOT NULL
  ),

  mart AS (
    SELECT DISTINCT
      IF(pais = 'colombia', 'Colombia', 'México') AS c,
      CAST(nid AS STRING)                         AS nid,
      dia                                         AS fecha
    FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
    WHERE pais IN ('colombia', 'mexico')
      -- Las 6 fuentes de marketing de cada país. CO tiene CRM(20) donde MX tiene
      -- Propiedades(46); el resto comparte código. Leadforms son 4 ids en CO (47/37/41/42)
      -- y uno solo en MX (47). Fuera de las 6 hay 0-2 leads/mes, pero el filtro va
      -- explícito porque ES la definición, no una limpieza de datos.
      AND (
        (pais = 'colombia' AND fuente_id_tig IN (3, 7, 20, 35, 39, 47, 37, 41, 42))
        OR
        (pais = 'mexico'   AND fuente_id_tig IN (3, 7, 46, 35, 39, 47))
      )
  ),

  eventos AS (
    SELECT c, fecha, CAST(nid AS STRING) AS nid, 'hist' AS universo, venia_inmo FROM base
    UNION ALL
    SELECT c, fecha, nid,                        'mart' AS universo, FALSE      FROM mart
  ),

  -- Cada evento se replica a sus 6 claves de período.
  expandido AS (
    SELECT e.c, e.nid, e.universo, e.venia_inmo, gp.g, gp.p
    FROM eventos e,
    UNNEST([
      STRUCT('D' AS g, CAST(e.fecha AS STRING) AS p),
      ('W', CAST(DATE_TRUNC(e.fecha, ISOWEEK) AS STRING)),
      ('C', CAST(DATE_TRUNC(e.fecha, WEEK(WEDNESDAY)) AS STRING)),
      ('M', FORMAT_DATE('%Y-%m', e.fecha)),
      ('Q', CONCAT(CAST(EXTRACT(YEAR FROM e.fecha) AS STRING), '-Q',
                   CAST(EXTRACT(QUARTER FROM e.fecha) AS STRING))),
      ('Y', CAST(EXTRACT(YEAR FROM e.fecha) AS STRING))
    ]) AS gp
  ),

  -- Últimos 25 períodos de cada (país, granularidad). El orden alfabético de `p` es
  -- cronológico en los 6 formatos: YYYY-MM-DD, YYYY-MM, YYYY-Qn y YYYY.
  vivos AS (
    SELECT c, g, p FROM (
      SELECT c, g, p, ROW_NUMBER() OVER (PARTITION BY c, g ORDER BY p DESC) AS rn
      FROM (SELECT DISTINCT c, g, p FROM expandido)
    ) WHERE rn <= 25
  )

SELECT
  e.g,
  e.c,
  e.p,
  -- NULL, no 0, donde un universo no tiene historia en ese período: el tablero pinta "—".
  IF(COUNTIF(e.universo = 'hist') = 0, NULL,
     COUNT(DISTINCT IF(e.universo = 'hist', e.nid, NULL)))                          AS asg,
  IF(COUNTIF(e.universo = 'hist') = 0, NULL,
     COUNT(DISTINCT IF(e.universo = 'hist' AND NOT e.venia_inmo, e.nid, NULL)))     AS directo,
  IF(COUNTIF(e.universo = 'hist') = 0, NULL,
     COUNT(DISTINCT IF(e.universo = 'hist' AND e.venia_inmo, e.nid, NULL)))         AS de_inmo,
  IF(COUNTIF(e.universo = 'mart') = 0, NULL,
     COUNT(DISTINCT IF(e.universo = 'mart', e.nid, NULL)))                          AS mart
FROM expandido e
JOIN vivos v ON v.c = e.c AND v.g = e.g AND v.p = e.p
GROUP BY e.g, e.c, e.p
ORDER BY e.g, e.c, e.p
