-- Hoja "Asignación de leads" · ASIGNADOS TOTALES (Colombia)
--
-- Cuántos leads se asignaron, calificaran o no para Market Maker. Es la fila que va debajo
-- de la tabla de definiciones oficiales, y su resta contra ella tiene que dar algo con
-- sentido: los asignados que no calificaban.
--
-- ⚠️ POR QUÉ NO ES "EL MART MENOS UN FILTRO"
--   El mart es una tabla materializada con sus 16 filtros ya aplicados; no se le puede
--   quitar uno. Hay que reconstruir la lógica desde `tabla_inmuebles_general`, y esa
--   reconstrucción NO reproduce el mart: medido 2026-09-10, ponerle los 4 filtros de
--   calificación da entre −1,8% y +4,2% contra el mart (abr 5.023 vs 5.080 · may 5.471 vs
--   5.250 · jul 5.053 vs 5.147 · ago 5.307 vs 5.398). Cuatro causas conocidas:
--     1. F15 es un PROXY. El filtro real es `asignacion_descartes_top IS NULL`, pero esa
--        tabla no es accesible por IAM; se usa `inmobiliaria != 1`, igual que en el tablero
--        `asignados-creacion`, donde ya está rotulado como proxy.
--     2. Los estados de la TIG son valores ACTUALES, no del momento de la asignación. Un
--        lead que calificaba al asignarse y cambió de estado después ya no pasa el filtro.
--        Es probablemente la causa principal, y explica que el signo sea mixto.
--     3. F4-F6 no están implementados: correos con `agente|delta|call`, los 5 hardcodeados,
--        y los 4 que exigen `contacto_digital` diligenciado.
--     4. F1/F2 se derivan distinto: el mart cuenta cambios de `hubspot_owner_id` en
--        `src_sellers_hubspot.history`; aquí se usa `fecha_primer_asignacion` de la TIG.
--
-- CÓMO SE RESUELVE: el total va ANCLADO al oficial.
--     total = mart_oficial + (recon_total − recon_calificados)
--   El segundo término es un estimador de diferencia sobre la MISMA base, así que el sesgo
--   común de las cuatro causas de arriba se cancela en buena parte. Y la propiedad que
--   importa se cumple por construcción: la porción calificada del total ES la cifra del
--   WBR, así que restar las dos filas de la tabla da los no-calificados y nada más.
--   Contra el conteo crudo de la reconstrucción difiere entre 0,7% y 2,8%.
--
-- ⚠️ ESTE NÚMERO NO ES CITABLE en el WBR ni en el OKR: ahí se reporta el mart. Sirve para
--   dimensionar la operación de asignación completa, no para medir el objetivo de Marketing.
--
-- SOLO COLOMBIA por ahora. La TIG de MX es el mismo esquema en
--   `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general`, con Propiedades(46) donde CO
--   tiene CRM(20) entre las 6 fuentes.
--
-- Salida larga: {g, c, p, asg} — mismo shape que asg_mm.sql y asg_inmo.sql.

WITH
  tig AS (
    SELECT
      CAST(t.nid AS STRING)                                AS nid,
      DATE(t.fecha_primer_asignacion)                      AS fecha,
      REPLACE(LOWER(TRIM(IFNULL(t.estado, ''))), '_', ' ') AS estado_norm,
      LOWER(TRIM(IFNULL(t.calificacion_del_lead_v2, '')))  AS calif,
      t.check_a_pricing,
      SAFE_CAST(t.inmobiliaria AS INT64)                   AS inmo_int
    FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` t
    LEFT JOIN `papyrus-data.habi_wh_bi.sc_users_hubspot` sc
      ON t.hubspot_owner_id = CAST(sc.id_segundario AS STRING)
    WHERE t.fecha_primer_asignacion IS NOT NULL
      AND t.nid IS NOT NULL
      AND t.fecha_creacion IS NOT NULL
      -- 6 fuentes de marketing CO. F3: el correo del comercial contiene "habi."
      AND t.fuente_id IN (3, 7, 20, 35, 39, 47, 37, 41, 42)
      AND LOWER(IFNULL(sc.email, t.hubspot_owner_id)) LIKE '%habi.%'
  ),

  -- Los 4 filtros de calificación MM, con las mismas condiciones que asignados-creacion.
  recon AS (
    SELECT
      nid, fecha,
      (estado_norm IN ('sin pricing incial', 'sin pricing inicial', 'no gestionado', 'cierre',
                       'no hay suficientes datos para comparar')
       AND check_a_pricing = 1
       AND (inmo_int IS NULL OR inmo_int = 0)
       AND calif NOT IN ('n', 'nh'))  AS es_calificado
    FROM tig
  ),

  mart AS (
    SELECT DISTINCT nid, dia AS fecha
    FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
    WHERE pais = 'colombia'
      AND fuente_id_tig IN (3, 7, 20, 35, 39, 47, 37, 41, 42)
  ),

  eventos AS (
    SELECT fecha, nid, 'recon' AS universo, es_calificado FROM recon
    UNION ALL
    SELECT fecha, CAST(nid AS STRING), 'mart', FALSE        FROM mart
  ),

  -- Mismos cortes que query.sql, asg_mm.sql y asg_inmo.sql:
  -- W = ISOWEEK (lun-dom) · C = WEEK(WEDNESDAY) = ciclo comercial (mié-mar).
  day_periods     AS (SELECT DISTINCT fecha                              p FROM eventos ORDER BY p DESC LIMIT 25),
  week_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, ISOWEEK)         p FROM eventos ORDER BY p DESC LIMIT 25),
  comm_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, WEEK(WEDNESDAY)) p FROM eventos ORDER BY p DESC LIMIT 25),
  month_periods   AS (SELECT DISTINCT DATE_TRUNC(fecha, MONTH)           p FROM eventos ORDER BY p DESC LIMIT 25),
  quarter_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, QUARTER)         p FROM eventos ORDER BY p DESC LIMIT 25),

  -- total = mart + (recon_total − recon_calificados). NULL si falta cualquiera de los dos
  -- universos en el período: la celda va en "—", no en cero.
  agg AS (
    SELECT 'D' g, CAST(fecha AS STRING) p,
      COUNTIF(universo = 'mart')                                          AS n_mart,
      COUNTIF(universo = 'recon')                                         AS n_recon,
      COUNTIF(universo = 'recon' AND es_calificado)                       AS n_calif
    FROM eventos WHERE fecha IN (SELECT p FROM day_periods) GROUP BY p
    UNION ALL
    SELECT 'W', CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING),
      COUNTIF(universo = 'mart'), COUNTIF(universo = 'recon'),
      COUNTIF(universo = 'recon' AND es_calificado)
    FROM eventos WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods)
    GROUP BY 2
    UNION ALL
    SELECT 'C', CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING),
      COUNTIF(universo = 'mart'), COUNTIF(universo = 'recon'),
      COUNTIF(universo = 'recon' AND es_calificado)
    FROM eventos WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods)
    GROUP BY 2
    UNION ALL
    SELECT 'M', FORMAT_DATE('%Y-%m', fecha),
      COUNTIF(universo = 'mart'), COUNTIF(universo = 'recon'),
      COUNTIF(universo = 'recon' AND es_calificado)
    FROM eventos WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods)
    GROUP BY 2
    UNION ALL
    SELECT 'Q', CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q',
                       CAST(EXTRACT(QUARTER FROM fecha) AS STRING)),
      COUNTIF(universo = 'mart'), COUNTIF(universo = 'recon'),
      COUNTIF(universo = 'recon' AND es_calificado)
    FROM eventos WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods)
    GROUP BY 2
    UNION ALL
    SELECT 'Y', CAST(EXTRACT(YEAR FROM fecha) AS STRING),
      COUNTIF(universo = 'mart'), COUNTIF(universo = 'recon'),
      COUNTIF(universo = 'recon' AND es_calificado)
    FROM eventos GROUP BY 2
  )

SELECT
  g,
  'Colombia' AS c,
  p,
  IF(n_mart = 0 OR n_recon = 0, NULL, n_mart + (n_recon - n_calif)) AS asg
FROM agg
ORDER BY g, p
