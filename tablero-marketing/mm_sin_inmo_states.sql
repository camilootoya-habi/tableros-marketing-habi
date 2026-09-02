-- Distribución por estado Inmo de los leads HOY calificados MM que nunca calificaron Inmo.
-- Clave para entender la violación MM⊆Inmo: dónde se atascan los leads que "no debería" haber.
-- Output: g, c, dim, f, p, state_id, state_name, n
--   dim='state' → estado Inmo actual · dim='cal2' → calificacion_del_lead_v2 de HubSpot
-- Denominador sugerido en frontend: cal_mm del período.

WITH
-- === fuente_detallada: separa WEB/Habímetro en Paid vs Non-Paid y aísla Marketing Loop ===
-- Espejo de ~/habi/queries/asignados_fuentes_paid_{co,mx}.sql, aplicado al universo de REGISTROS.
-- Paid sale del diccionario UTM (Google Sheet): tabla_inmuebles_general.campana_mercadeo unido a
-- registro_unico_utm_mkt_*.campana_mercadeo_original. Se miran los DOS campos a propósito:
-- `mkt_media='Paid'` capta 'WEB Triada' y 'Brand' (pagos con otro nombre de canal), y el LIKE capta
-- las campañas de 'WEB Paid' que quedaron con mkt_media='Otro'.
-- El diccionario trae campañas repetidas → QUALIFY para deduplicar; sin eso el join multiplica filas.
-- Marketing Loop NO es una fuente en TIG: son leads recreados que entran como WEB (y algunos como
-- Leadform/Habímetro). La única marca es la utm_campaign de HubSpot y GANA sobre la fuente original,
-- porque es re-gestión y no lead nuevo.
-- Diferencias vs la query de asignados: acá SÍ existe `propiedades` (46, solo MX), y `crm` trae solo
-- el 20 porque el tablero siempre excluye Ventana (fuente_id=1).
utm_co AS (
  SELECT campana_mercadeo_original, mkt_channel_medium, mkt_media
  FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY campana_mercadeo_original ORDER BY campana_mercadeo_original) = 1
),
utm_mx AS (
  SELECT campana_mercadeo_original, mkt_channel_medium, mkt_media
  FROM `sellers-main-prod.bi_mx.registro_unico_utm_mkt_mexico`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY campana_mercadeo_original ORDER BY campana_mercadeo_original) = 1
),
loop_nids AS (
  SELECT DISTINCT country AS c, nid
  FROM `sellers-main-prod.hubspot.deals`
  WHERE utm_campaign LIKE '%reinteresados%' AND nid IS NOT NULL
),
base AS (
  SELECT 'Colombia' AS c,
  CASE
    WHEN lp.nid IS NOT NULL THEN 'loop'
    WHEN tig.fuente_id = 3  THEN IF(COALESCE(u.mkt_media = 'Paid' OR u.mkt_channel_medium LIKE '% Paid', FALSE), 'web_paid', 'web_np')
    WHEN tig.fuente_id = 7  THEN IF(COALESCE(u.mkt_media = 'Paid' OR u.mkt_channel_medium LIKE '% Paid', FALSE), 'habi_paid', 'habi_np')
    WHEN tig.fuente_id = 47 THEN 'leadforms'
    WHEN tig.fuente_id = 20 THEN 'crm'
    WHEN tig.fuente_id = 46 THEN 'propiedades'
    WHEN tig.fuente_id = 39 THEN 'brokers'
    WHEN tig.fuente_id = 35 THEN 'comercial'
    ELSE 'otros'
  END AS fuente_id,
    DATE(tig.fecha_creacion) AS fecha,
    CAST(tig.nid AS STRING) AS nid,
    tig.negocio_id AS biz_id,
    tni.last_state_id_real_estate AS inmo_state,
    tni.last_estado_id AS mm_state
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` tni ON tni.id = tig.negocio_id
  LEFT JOIN utm_co u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'Colombia'
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 20, 35, 39, 47)

  UNION ALL

  SELECT 'México' AS c,
  CASE
    WHEN lp.nid IS NOT NULL THEN 'loop'
    WHEN tig.fuente_id = 3  THEN IF(COALESCE(u.mkt_media = 'Paid' OR u.mkt_channel_medium LIKE '% Paid', FALSE), 'web_paid', 'web_np')
    WHEN tig.fuente_id = 7  THEN IF(COALESCE(u.mkt_media = 'Paid' OR u.mkt_channel_medium LIKE '% Paid', FALSE), 'habi_paid', 'habi_np')
    WHEN tig.fuente_id = 47 THEN 'leadforms'
    WHEN tig.fuente_id = 20 THEN 'crm'
    WHEN tig.fuente_id = 46 THEN 'propiedades'
    WHEN tig.fuente_id = 39 THEN 'brokers'
    WHEN tig.fuente_id = 35 THEN 'comercial'
    ELSE 'otros'
  END AS fuente_id,
    DATE(tig.fecha_creacion) AS fecha,
    CAST(tig.nid AS STRING) AS nid,
    tig.id_negocio AS biz_id,
    tni.last_state_id_real_estate AS inmo_state,
    tni.last_state_id AS mm_state
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_property_deal` tni ON tni.id = tig.id_negocio
  LEFT JOIN utm_mx u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'México'
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 35, 39, 46, 47)
),

cal_inmo AS (
  SELECT 'Colombia' AS c, deal_id AS biz_id
  FROM `sellers-main-prod.co_rds_staging.habi_db_history_state_real_estate`
  WHERE state_id = 20 AND deal_id IS NOT NULL
  GROUP BY c, biz_id
  UNION ALL
  SELECT 'México' AS c, deal_id AS biz_id
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state_real_estate`
  WHERE state_id = 20 AND deal_id IS NOT NULL
  GROUP BY c, biz_id
),

-- Universo del Error de Buybox, deliberadamente ASIMÉTRICO:
--   MM en PRESENTE  → estado actual IN (20,63): mide el inventario vivo, y así los leads
--                     que después se murieron (sobre todo duplicados) no inflan el error.
--   Inmo en NUNCA   → sin ningún evento de state_id=20 en el histórico de Inmo: la pregunta
--                     es si el buybox de Inmo lo aceptó ALGUNA VEZ.
-- Si Inmo también se midiera en presente, entrarían los que calificaron Inmo y después se
-- desclasificaron — y eso ya lo mide "Error de consistencia Inmo". Se contarían dos veces.
-- Calificación comercial del lead (snapshot de HubSpot, sin fecha: es el valor de HOY,
-- no necesariamente el que tenía cuando el BB de Inmo lo descartó).
-- Taxonomías distintas por país: CO usa HesH / baby HesH / NH / A / P / n; MX es casi todo A.
deal_cal AS (
  SELECT CAST(nid AS STRING) AS nid, ANY_VALUE(calificacion_del_lead_v2) AS cal2
  FROM `sellers-main-prod.hubspot.deals`
  WHERE nid IS NOT NULL
  GROUP BY 1
),

-- Asignación EVER por producto. El producto sale del `equipo_inicial` del evento
-- ('inmo' en el nombre marca Inmobiliaria, incluido 'gabi inmobiliaria'); el resto es MM.
-- Incluye asignaciones a GABI y a comercial humano.
-- ⚠️ NO son excluyentes: un lead puede estar asignado a los dos productos, así que estas
-- filas NO suman el total — a diferencia de los bloques de estado y de calificación.
asig AS (
  SELECT c, nid,
    LOGICAL_OR(NOT es_inmo) AS ever_mm,
    LOGICAL_OR(es_inmo)     AS ever_inmo
  FROM (
    SELECT 'México' c, CAST(nid AS STRING) nid,
           LOWER(TRIM(IFNULL(equipo_inicial, ''))) LIKE '%inmo%' es_inmo
    FROM `sellers-main-prod.bi_mx.seguimiento_asignacion_ibuyer`
    UNION ALL
    SELECT 'Colombia', CAST(nid AS STRING),
           LOWER(TRIM(IFNULL(equipo_inicial, ''))) LIKE '%inmo%'
    FROM `sellers-main-prod.bi_co.seguimiento_asignacion_ibuyer_co`
  )
  GROUP BY 1, 2
),

candidates AS (
  SELECT b.c, b.fuente_id, b.fecha, b.inmo_state,
         COALESCE(NULLIF(TRIM(dc.cal2), ''), '(sin calificación)') AS cal2,
         IFNULL(ag.ever_mm, FALSE)   AS ever_mm,
         IFNULL(ag.ever_inmo, FALSE) AS ever_inmo
  FROM base b
  LEFT JOIN cal_inmo i ON i.c = b.c AND i.biz_id = b.biz_id
  LEFT JOIN deal_cal dc ON dc.nid = b.nid
  LEFT JOIN asig ag ON ag.c = b.c AND ag.nid = b.nid
  WHERE b.mm_state IN (20, 63)
    AND i.biz_id IS NULL
),

catalog AS (
  SELECT id, estado FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_estados`
),

day_periods AS (SELECT DISTINCT fecha FROM candidates ORDER BY fecha DESC LIMIT 25),
week_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, ISOWEEK) p FROM candidates ORDER BY p DESC LIMIT 25),
comm_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, WEEK(WEDNESDAY)) p FROM candidates ORDER BY p DESC LIMIT 25),
month_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, MONTH) p FROM candidates ORDER BY p DESC LIMIT 25),
quarter_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, QUARTER) p FROM candidates ORDER BY p DESC LIMIT 25),

daily AS (
  SELECT 'D' g, c, 'state' dim, fuente_id f, CAST(fecha AS STRING) p, CAST(inmo_state AS STRING) v, COUNT(*) n
  FROM candidates WHERE fecha IN (SELECT fecha FROM day_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'D' g, c, 'cal2', fuente_id, CAST(fecha AS STRING), cal2, COUNT(*)
  FROM candidates WHERE fecha IN (SELECT fecha FROM day_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'D', c, 'asig', fuente_id, CAST(fecha AS STRING), 'Ever asignado a Market Maker', COUNTIF(ever_mm)
  FROM candidates WHERE fecha IN (SELECT fecha FROM day_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'D', c, 'asig', fuente_id, CAST(fecha AS STRING), 'Ever asignado a Inmobiliaria', COUNTIF(ever_inmo)
  FROM candidates WHERE fecha IN (SELECT fecha FROM day_periods) GROUP BY 1,2,3,4,5,6
),
weekly AS (
  SELECT 'W' g, c, 'state' dim, fuente_id f, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING) p, CAST(inmo_state AS STRING) v, COUNT(*) n
  FROM candidates WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'W' g, c, 'cal2', fuente_id, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING), cal2, COUNT(*)
  FROM candidates WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'W', c, 'asig', fuente_id, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING), 'Ever asignado a Market Maker', COUNTIF(ever_mm)
  FROM candidates WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'W', c, 'asig', fuente_id, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING), 'Ever asignado a Inmobiliaria', COUNTIF(ever_inmo)
  FROM candidates WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY 1,2,3,4,5,6
),
commercial AS (
  SELECT 'C' g, c, 'state' dim, fuente_id f, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING) p, CAST(inmo_state AS STRING) v, COUNT(*) n
  FROM candidates WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'C' g, c, 'cal2', fuente_id, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING), cal2, COUNT(*)
  FROM candidates WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'C', c, 'asig', fuente_id, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING), 'Ever asignado a Market Maker', COUNTIF(ever_mm)
  FROM candidates WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'C', c, 'asig', fuente_id, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING), 'Ever asignado a Inmobiliaria', COUNTIF(ever_inmo)
  FROM candidates WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY 1,2,3,4,5,6
),
monthly AS (
  SELECT 'M' g, c, 'state' dim, fuente_id f, FORMAT_DATE('%Y-%m', fecha) p, CAST(inmo_state AS STRING) v, COUNT(*) n
  FROM candidates WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'M' g, c, 'cal2', fuente_id, FORMAT_DATE('%Y-%m', fecha), cal2, COUNT(*)
  FROM candidates WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'M', c, 'asig', fuente_id, FORMAT_DATE('%Y-%m', fecha), 'Ever asignado a Market Maker', COUNTIF(ever_mm)
  FROM candidates WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'M', c, 'asig', fuente_id, FORMAT_DATE('%Y-%m', fecha), 'Ever asignado a Inmobiliaria', COUNTIF(ever_inmo)
  FROM candidates WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY 1,2,3,4,5,6
),
quarterly AS (
  SELECT 'Q' g, c, 'state' dim, fuente_id f,
    CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)) p,
    CAST(inmo_state AS STRING) v, COUNT(*) n
  FROM candidates WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'Q', c, 'cal2', fuente_id,
    CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)),
    cal2, COUNT(*)
  FROM candidates WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'Q', c, 'asig', fuente_id, CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)), 'Ever asignado a Market Maker', COUNTIF(ever_mm)
  FROM candidates WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'Q', c, 'asig', fuente_id, CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)), 'Ever asignado a Inmobiliaria', COUNTIF(ever_inmo)
  FROM candidates WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY 1,2,3,4,5,6
),
yearly AS (
  SELECT 'Y' g, c, 'state' dim, fuente_id f, CAST(EXTRACT(YEAR FROM fecha) AS STRING) p, CAST(inmo_state AS STRING) v, COUNT(*) n
  FROM candidates WHERE TRUE GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'Y' g, c, 'cal2', fuente_id, CAST(EXTRACT(YEAR FROM fecha) AS STRING), cal2, COUNT(*)
  FROM candidates WHERE TRUE GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'Y', c, 'asig', fuente_id, CAST(EXTRACT(YEAR FROM fecha) AS STRING), 'Ever asignado a Market Maker', COUNTIF(ever_mm)
  FROM candidates WHERE TRUE GROUP BY 1,2,3,4,5,6
  UNION ALL
  SELECT 'Y', c, 'asig', fuente_id, CAST(EXTRACT(YEAR FROM fecha) AS STRING), 'Ever asignado a Inmobiliaria', COUNTIF(ever_inmo)
  FROM candidates WHERE TRUE GROUP BY 1,2,3,4,5,6
),

all_rows AS (
  SELECT * FROM daily
  UNION ALL SELECT * FROM weekly
  UNION ALL SELECT * FROM commercial
  UNION ALL SELECT * FROM monthly
  UNION ALL SELECT * FROM quarterly
  UNION ALL SELECT * FROM yearly
)

SELECT
  a.g, a.c, a.f, a.p,
  a.dim,
  COALESCE(SAFE_CAST(a.v AS INT64), -1) AS state_id,
  CASE WHEN a.dim IN ('cal2', 'asig') THEN a.v
       ELSE COALESCE(cat.estado, IF(a.v IS NULL, '(sin registro Inmo)', CONCAT('state_', a.v))) END AS state_name,
  a.n
FROM all_rows a
LEFT JOIN catalog cat ON a.dim = 'state' AND cat.id = SAFE_CAST(a.v AS INT64)
ORDER BY a.g, a.c, a.dim, a.f, a.p, a.n DESC
