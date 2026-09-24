-- Estado ACTUAL de los leads que fueron calificados MM y ya no lo están.
-- Alimenta la tabla "Control de calidad": fila 1 = total, y debajo el desglose por estado
-- actual ordenado de mayor a menor.
--
-- Desclasificado MM = pasó alguna vez por estado 20 o 63 en el histórico de MM, y su estado
-- ACTUAL (last_estado_id CO / last_state_id MX) ya no es 20 ni 63.
-- Verificado 2026-08-11: en este universo NO aparece ningún estado de las etapas 4/5/6
-- (avance comercial), solo 1, 2 y 3 — coherente con que el estado 20 es terminal y el avance
-- del funnel vive en `etapa` / oportunidad de negocio, no en el estado.
--
-- Output: g, c, f, p, state_id, state_name, n   (mismo contrato que antifunnel.json)
-- Cohorte por fecha_creacion, mismos filtros de fuente que query.sql.

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
    tig.negocio_id AS biz_id,
    tni.last_estado_id AS cur_state
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN utm_co u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'Colombia'
  LEFT JOIN `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` tni ON tni.id = tig.negocio_id
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
    tig.id_negocio AS biz_id,
    tni.last_state_id AS cur_state
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN utm_mx u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'México'
  LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_property_deal` tni ON tni.id = tig.id_negocio
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 35, 39, 46, 47)
),

-- alguna vez calificado MM (histórico)
cal_mm AS (
  SELECT 'Colombia' AS c, negocio_id AS biz_id
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
  WHERE estado_id IN (20, 63) AND negocio_id IS NOT NULL
  GROUP BY biz_id
  UNION ALL
  SELECT 'México', deal_id
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
  WHERE state_id IN (20, 63) AND deal_id IS NOT NULL
  GROUP BY deal_id
),

desclas AS (
  SELECT b.c, b.fuente_id, b.fecha, b.cur_state
  FROM base b
  JOIN cal_mm m ON m.c = b.c AND m.biz_id = b.biz_id
  WHERE b.cur_state IS NOT NULL AND b.cur_state NOT IN (20, 63)
),

-- Solo los últimos 25 períodos de cada granularidad — mismo criterio que antifunnel.sql.
-- Sin esto el JSON pesa ~9,7 MB: la granularidad diaria × 10 fuentes × 2 países explota.
day_periods     AS (SELECT DISTINCT fecha FROM desclas ORDER BY fecha DESC LIMIT 25),
week_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, ISOWEEK) p FROM desclas ORDER BY p DESC LIMIT 25),
comm_periods    AS (SELECT DISTINCT DATE_TRUNC(fecha, WEEK(WEDNESDAY)) p FROM desclas ORDER BY p DESC LIMIT 25),
month_periods   AS (SELECT DISTINCT DATE_TRUNC(fecha, MONTH) p FROM desclas ORDER BY p DESC LIMIT 25),
quarter_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, QUARTER) p FROM desclas ORDER BY p DESC LIMIT 25),

catalog AS (
  SELECT id, estado FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_estados`
),

daily      AS (SELECT 'D' g, c, fuente_id f, CAST(fecha AS STRING) p, cur_state state_id, COUNT(*) n FROM desclas WHERE fecha IN (SELECT fecha FROM day_periods) GROUP BY 1,2,3,4,5),
weekly     AS (SELECT 'W' g, c, fuente_id f, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING) p, cur_state state_id, COUNT(*) n FROM desclas WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY 1,2,3,4,5),
commercial AS (SELECT 'C' g, c, fuente_id f, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING) p, cur_state state_id, COUNT(*) n FROM desclas WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY 1,2,3,4,5),
monthly    AS (SELECT 'M' g, c, fuente_id f, FORMAT_DATE('%Y-%m', fecha) p, cur_state state_id, COUNT(*) n FROM desclas WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY 1,2,3,4,5),
quarterly  AS (SELECT 'Q' g, c, fuente_id f, CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)) p, cur_state state_id, COUNT(*) n FROM desclas WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY 1,2,3,4,5),
yearly     AS (SELECT 'Y' g, c, fuente_id f, CAST(EXTRACT(YEAR FROM fecha) AS STRING) p, cur_state state_id, COUNT(*) n FROM desclas GROUP BY 1,2,3,4,5),

all_rows AS (
  SELECT * FROM daily UNION ALL SELECT * FROM weekly UNION ALL SELECT * FROM commercial
  UNION ALL SELECT * FROM monthly UNION ALL SELECT * FROM quarterly UNION ALL SELECT * FROM yearly
)

SELECT a.g, a.c, a.f, a.p, a.state_id,
  COALESCE(cat.estado, CONCAT('state_', CAST(a.state_id AS STRING))) AS state_name,
  a.n
FROM all_rows a
LEFT JOIN catalog cat ON cat.id = a.state_id
ORDER BY a.g, a.c, a.f, a.p, a.n DESC
