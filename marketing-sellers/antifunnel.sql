-- Antifunnel Sellers (CO + MX)
-- Por cada combinación de país, fuente, temporalidad y estado actual (last_estado_id)
-- cuenta los leads NO calificados (estado ≠ 20, 63) agrupados por fecha_creacion.
-- Output: g, c, bb, f, p, state_id, state_name, n
--   bb = 'mm'   → estado actual del BB de Market Maker, no calificado = NOT IN (20, 63)
--   bb = 'inmo' → estado actual del BB de Inmobiliaria (last_state_id_real_estate), no calificado = <> 20
-- Respeta los mismos filtros de fuente y ventanas que query.sql.

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
    'mm' AS bb,
    tni.last_estado_id AS state_id
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` tni ON tni.id = tig.negocio_id
  LEFT JOIN utm_co u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'Colombia'
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 20, 35, 39, 47)
    AND tni.last_estado_id IS NOT NULL
    AND tni.last_estado_id NOT IN (20, 63)

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
    'mm' AS bb,
    tni.last_state_id AS state_id
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_property_deal` tni ON tni.id = tig.id_negocio
  LEFT JOIN utm_mx u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'México'
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 35, 39, 46, 47)
    AND tni.last_state_id IS NOT NULL
    AND tni.last_state_id NOT IN (20, 63)

  UNION ALL

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
    'inmo' AS bb,
    tni.last_state_id_real_estate AS state_id
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` tni ON tni.id = tig.negocio_id
  LEFT JOIN utm_co u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'Colombia'
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 20, 35, 39, 47)
    AND tni.last_state_id_real_estate IS NOT NULL
    AND tni.last_state_id_real_estate <> 20

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
    'inmo' AS bb,
    tni.last_state_id_real_estate AS state_id
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_property_deal` tni ON tni.id = tig.id_negocio
  LEFT JOIN utm_mx u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'México'
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 35, 39, 46, 47)
    AND tni.last_state_id_real_estate IS NOT NULL
    AND tni.last_state_id_real_estate <> 20
),

catalog AS (
  SELECT id, estado FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_estados`
),

day_periods AS (SELECT DISTINCT fecha FROM base ORDER BY fecha DESC LIMIT 25),
week_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, ISOWEEK) p FROM base ORDER BY p DESC LIMIT 25),
comm_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, WEEK(WEDNESDAY)) p FROM base ORDER BY p DESC LIMIT 25),
month_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, MONTH) p FROM base ORDER BY p DESC LIMIT 25),
quarter_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, QUARTER) p FROM base ORDER BY p DESC LIMIT 25),

daily AS (
  SELECT 'D' g, c, bb, fuente_id f, CAST(fecha AS STRING) p, state_id, COUNT(*) n
  FROM base WHERE fecha IN (SELECT fecha FROM day_periods) GROUP BY c, bb, f, p, state_id
),
weekly AS (
  SELECT 'W' g, c, bb, fuente_id f, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING) p, state_id, COUNT(*) n
  FROM base WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY c, bb, f, p, state_id
),
commercial AS (
  SELECT 'C' g, c, bb, fuente_id f, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING) p, state_id, COUNT(*) n
  FROM base WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY c, bb, f, p, state_id
),
monthly AS (
  SELECT 'M' g, c, bb, fuente_id f, FORMAT_DATE('%Y-%m', fecha) p, state_id, COUNT(*) n
  FROM base WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY c, bb, f, p, state_id
),
quarterly AS (
  SELECT 'Q' g, c, bb, fuente_id f,
    CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)) p,
    state_id, COUNT(*) n
  FROM base WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY c, bb, f, p, state_id
),
yearly AS (
  SELECT 'Y' g, c, bb, fuente_id f, CAST(EXTRACT(YEAR FROM fecha) AS STRING) p, state_id, COUNT(*) n
  FROM base GROUP BY c, bb, f, p, state_id
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
  a.g, a.c, a.bb, a.f, a.p,
  a.state_id,
  COALESCE(cat.estado, CONCAT('state_', CAST(a.state_id AS STRING))) AS state_name,
  a.n
FROM all_rows a
LEFT JOIN catalog cat ON cat.id = a.state_id
ORDER BY a.g, a.c, a.bb, a.f, a.p, a.n DESC
