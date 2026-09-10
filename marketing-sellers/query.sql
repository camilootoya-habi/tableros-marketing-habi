-- Funnel Sellers (CO + MX) — Cohort por fecha de creación
-- Campos por fila: g, c, f, fn, p, tr, t, cal_mm, cal_inmo, asg_inmo, cal_mm_no_inmo, cal_mm_dup, cal_mm_desc, incomp, dup
--   tr             = Registros totales (COUNT(*), por fecha_creacion)
--   t              = Registros con NID (COUNT DISTINCT nid, por fecha_creacion)
--   cal_mm         = leads creados en el período que alguna vez fueron calificados MM
--   cal_inmo       = leads creados en el período que alguna vez fueron calificados Inmo
--   asg_inmo       = leads creados en el período que alguna vez tuvieron Primer asignación dentro del funnel Inmo
--   cal_mm_no_inmo = HOY calificados MM (estado actual IN 20,63) que NUNCA calificaron Inmo
--     → "Error de Buybox" (violación MM⊆Inmo). Asimétrico a propósito: MM en presente para
--     medir inventario vivo (los duplicados y descartes posteriores no inflan el error),
--     Inmo en "nunca" porque la pregunta es si el buybox de Inmo lo aceptó alguna vez.
--     Medirlo en presente de los dos lados metería los desclasificados Inmo, que ya cuenta
--     "Error de consistencia Inmo" → doble conteo.
--   cal_desclas    = calificaron Inmo alguna vez y su estado ACTUAL de Inmo ya no es 20 → "Error de consistencia (Inmo)"
--     Simétrico a cal_mm_desclas. Verificado 2026-08-11: da idéntico al último evento del
--     histórico (343 MX / 160 CO en cosechas desde may-26) porque la tabla histórica de Inmo
--     solo guarda decisiones del BB — el último evento ES el estado actual.
--   cal_mm_desclas = calificaron MM alguna vez y su estado ACTUAL ya no es 20 ni 63 → "Error de consistencia (MM)"
--     Verificado 2026-08-11: entre los calificados MM que hoy están en otro estado NO aparece
--     ningún estado de las etapas 4/5/6 (avance comercial) — solo etapas 1, 2 y 3 (intake y
--     backbone). Coherente con que el estado 20 es terminal y el avance vive en `etapa` /
--     oportunidad de negocio. Por eso "estado actual ∉ (20,63)" ES desclasificación, sin
--     necesidad de restringir a la etapa del BB.
--   cal_mm_dup     = calificaron MM y su estado actual es duplicado (1)
--   cal_mm_desc    = calificaron MM y su estado actual es descarte tardío (3,10,16,33,38,55,56,61,64)
--   incomp         = estado actual = 7 (incompleto)
--   dup            = estado actual = 1 (duplicado)
-- Calificado MM: estado_id IN (20, 63). Calificado Inmo: state_id = 20.
-- ⚠️ Estos estados son TERMINALES en el backbone: el estado nunca avanza más allá de
--    la calificación. El estado es el PRIMER campo del funnel (registro → calificado);
--    el avance posterior vive en `etapa` / oportunidad de negocio / dealstage, no acá.
-- Asignado Inmo: primer evento valor='Primer_asigancion' (CO) / 'Primer asignacion' (MX) dentro de equipos Inmo.

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
  SELECT 'Colombia' AS c, tig.nid,
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
    DATE(tig.fecha_creacion) AS fecha, tig.negocio_id AS biz_id
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN utm_co u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'Colombia'
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 20, 35, 39, 47)

  UNION ALL

  SELECT 'México' AS c, tig.nid,
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
    DATE(tig.fecha_creacion) AS fecha, tig.id_negocio AS biz_id
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN utm_mx u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'México'
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 35, 39, 46, 47)
),

cal_mm_dates AS (
  SELECT 'Colombia' AS c, negocio_id AS biz_id, MIN(DATE(fecha_actualizacion)) AS ev_date
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
  WHERE estado_id IN (20, 63) AND negocio_id IS NOT NULL
  GROUP BY c, biz_id

  UNION ALL

  SELECT 'México' AS c, deal_id AS biz_id, MIN(DATE(date_create)) AS ev_date
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
  WHERE state_id IN (20, 63) AND deal_id IS NOT NULL
  GROUP BY c, biz_id
),

cal_inmo_dates AS (
  SELECT 'Colombia' AS c, deal_id AS biz_id, MIN(DATE(date_create)) AS ev_date
  FROM `sellers-main-prod.co_rds_staging.habi_db_history_state_real_estate`
  WHERE state_id = 20 AND deal_id IS NOT NULL
  GROUP BY c, biz_id

  UNION ALL

  SELECT 'México' AS c, deal_id AS biz_id, MIN(DATE(date_create)) AS ev_date
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state_real_estate`
  WHERE state_id = 20 AND deal_id IS NOT NULL
  GROUP BY c, biz_id
),

-- Asignados Inmo: primer evento de Primer asignación dentro de equipos Inmo del país.
-- CO: equipo_sellers='Exclusivo inmobiliaria CO', valor='Primer_asigancion' (typo histórico).
-- MX: equipo IN ('Inmobiliaria 1','Inmobiliaria 2','Inmo ciudades MX','Inmobliaria mx','Inmo puebla'), valor='Primer asignacion'.
asg_inmo_dates AS (
  SELECT 'Colombia' AS c, nid, MIN(DATE(fecha)) AS ev_date
  FROM `papyrus-data.habi_wh_bi.funnel_diarios_col`
  WHERE equipo_sellers = 'Exclusivo inmobiliaria CO'
    AND valor = 'Primer_asigancion'
    AND nid IS NOT NULL
  GROUP BY c, nid

  UNION ALL

  SELECT 'México' AS c, nid, MIN(DATE(fecha)) AS ev_date
  FROM `sellers-main-prod.bi_mx.seguimiento_funnel_mex`
  WHERE equipo IN ('Inmobiliaria 1','Inmobiliaria 2','Inmo ciudades MX','Inmobliaria mx','Inmo puebla')
    AND valor = 'Primer asignacion'
    AND nid IS NOT NULL
  GROUP BY c, nid
),

-- Estado actual del lead (MM) en OLTP, por país
current_state AS (
  SELECT 'Colombia' AS c, id AS biz_id, last_estado_id AS st, last_state_id_real_estate AS st_inmo
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble`
  UNION ALL
  SELECT 'México' AS c, id AS biz_id, last_state_id AS st, last_state_id_real_estate AS st_inmo
  FROM `sellers-main-prod.mx_rds_staging.habi_db_property_deal`
),

enriched AS (
  SELECT b.c, b.nid, b.fuente_id, b.fecha,
    mc.ev_date AS cal_mm_date,
    ic.ev_date AS cal_inmo_date,
    ai.ev_date AS asg_inmo_date,
    cs.st AS cur_state,
    cs.st_inmo AS cur_inmo_state,
  FROM base b
  LEFT JOIN cal_mm_dates mc ON mc.c = b.c AND mc.biz_id = b.biz_id
  LEFT JOIN cal_inmo_dates ic ON ic.c = b.c AND ic.biz_id = b.biz_id
  LEFT JOIN asg_inmo_dates ai ON ai.c = b.c AND ai.nid = b.nid
  LEFT JOIN current_state cs ON cs.c = b.c AND cs.biz_id = b.biz_id
),

day_periods AS (SELECT DISTINCT fecha FROM enriched ORDER BY fecha DESC LIMIT 25),
week_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, ISOWEEK) p FROM enriched ORDER BY p DESC LIMIT 25),
comm_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, WEEK(WEDNESDAY)) p FROM enriched ORDER BY p DESC LIMIT 25),
month_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, MONTH) p FROM enriched ORDER BY p DESC LIMIT 25),
quarter_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, QUARTER) p FROM enriched ORDER BY p DESC LIMIT 25),

-- COHORT (group by fecha_creacion)
cohort_daily AS (
  SELECT 'D' g, c, fuente_id f, CAST(fecha AS STRING) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(cal_mm_date IS NOT NULL) cal_mm,
    COUNTIF(cal_inmo_date IS NOT NULL) cal_inmo,
    COUNTIF(asg_inmo_date IS NOT NULL) asg_inmo,
    COUNTIF(cur_state IN (20, 63) AND cal_inmo_date IS NULL) cal_mm_no_inmo,
    COUNTIF(cal_inmo_date IS NOT NULL AND cur_inmo_state IS NOT NULL AND cur_inmo_state <> 20) cal_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IS NOT NULL AND cur_state NOT IN (20, 63)) cal_mm_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state = 1) cal_mm_dup,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IN (3,10,16,33,38,55,56,61,64)) cal_mm_desc,
    COUNTIF(cur_state = 7) incomp,
    COUNTIF(cur_state = 1) dup
  FROM enriched WHERE fecha IN (SELECT fecha FROM day_periods) GROUP BY c, f, p
),
cohort_weekly AS (
  SELECT 'W' g, c, fuente_id f, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(cal_mm_date IS NOT NULL) cal_mm,
    COUNTIF(cal_inmo_date IS NOT NULL) cal_inmo,
    COUNTIF(asg_inmo_date IS NOT NULL) asg_inmo,
    COUNTIF(cur_state IN (20, 63) AND cal_inmo_date IS NULL) cal_mm_no_inmo,
    COUNTIF(cal_inmo_date IS NOT NULL AND cur_inmo_state IS NOT NULL AND cur_inmo_state <> 20) cal_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IS NOT NULL AND cur_state NOT IN (20, 63)) cal_mm_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state = 1) cal_mm_dup,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IN (3,10,16,33,38,55,56,61,64)) cal_mm_desc,
    COUNTIF(cur_state = 7) incomp,
    COUNTIF(cur_state = 1) dup
  FROM enriched WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY c, f, p
),
cohort_commercial AS (
  SELECT 'C' g, c, fuente_id f, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(cal_mm_date IS NOT NULL) cal_mm,
    COUNTIF(cal_inmo_date IS NOT NULL) cal_inmo,
    COUNTIF(asg_inmo_date IS NOT NULL) asg_inmo,
    COUNTIF(cur_state IN (20, 63) AND cal_inmo_date IS NULL) cal_mm_no_inmo,
    COUNTIF(cal_inmo_date IS NOT NULL AND cur_inmo_state IS NOT NULL AND cur_inmo_state <> 20) cal_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IS NOT NULL AND cur_state NOT IN (20, 63)) cal_mm_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state = 1) cal_mm_dup,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IN (3,10,16,33,38,55,56,61,64)) cal_mm_desc,
    COUNTIF(cur_state = 7) incomp,
    COUNTIF(cur_state = 1) dup
  FROM enriched WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY c, f, p
),
cohort_monthly AS (
  SELECT 'M' g, c, fuente_id f, FORMAT_DATE('%Y-%m', fecha) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(cal_mm_date IS NOT NULL) cal_mm,
    COUNTIF(cal_inmo_date IS NOT NULL) cal_inmo,
    COUNTIF(asg_inmo_date IS NOT NULL) asg_inmo,
    COUNTIF(cur_state IN (20, 63) AND cal_inmo_date IS NULL) cal_mm_no_inmo,
    COUNTIF(cal_inmo_date IS NOT NULL AND cur_inmo_state IS NOT NULL AND cur_inmo_state <> 20) cal_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IS NOT NULL AND cur_state NOT IN (20, 63)) cal_mm_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state = 1) cal_mm_dup,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IN (3,10,16,33,38,55,56,61,64)) cal_mm_desc,
    COUNTIF(cur_state = 7) incomp,
    COUNTIF(cur_state = 1) dup
  FROM enriched WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY c, f, p
),
cohort_quarterly AS (
  SELECT 'Q' g, c, fuente_id f,
    CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(cal_mm_date IS NOT NULL) cal_mm,
    COUNTIF(cal_inmo_date IS NOT NULL) cal_inmo,
    COUNTIF(asg_inmo_date IS NOT NULL) asg_inmo,
    COUNTIF(cur_state IN (20, 63) AND cal_inmo_date IS NULL) cal_mm_no_inmo,
    COUNTIF(cal_inmo_date IS NOT NULL AND cur_inmo_state IS NOT NULL AND cur_inmo_state <> 20) cal_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IS NOT NULL AND cur_state NOT IN (20, 63)) cal_mm_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state = 1) cal_mm_dup,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IN (3,10,16,33,38,55,56,61,64)) cal_mm_desc,
    COUNTIF(cur_state = 7) incomp,
    COUNTIF(cur_state = 1) dup
  FROM enriched WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY c, f, p
),
cohort_yearly AS (
  SELECT 'Y' g, c, fuente_id f, CAST(EXTRACT(YEAR FROM fecha) AS STRING) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(cal_mm_date IS NOT NULL) cal_mm,
    COUNTIF(cal_inmo_date IS NOT NULL) cal_inmo,
    COUNTIF(asg_inmo_date IS NOT NULL) asg_inmo,
    COUNTIF(cur_state IN (20, 63) AND cal_inmo_date IS NULL) cal_mm_no_inmo,
    COUNTIF(cal_inmo_date IS NOT NULL AND cur_inmo_state IS NOT NULL AND cur_inmo_state <> 20) cal_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IS NOT NULL AND cur_state NOT IN (20, 63)) cal_mm_desclas,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state = 1) cal_mm_dup,
    COUNTIF(cal_mm_date IS NOT NULL AND cur_state IN (3,10,16,33,38,55,56,61,64)) cal_mm_desc,
    COUNTIF(cur_state = 7) incomp,
    COUNTIF(cur_state = 1) dup
  FROM enriched GROUP BY c, f, p
)

SELECT g, c, f, p, tr, t, cal_mm, cal_inmo, asg_inmo, cal_mm_no_inmo, cal_desclas, cal_mm_desclas, cal_mm_dup, cal_mm_desc, incomp, dup
FROM (
  SELECT * FROM cohort_daily UNION ALL SELECT * FROM cohort_weekly UNION ALL SELECT * FROM cohort_commercial
  UNION ALL SELECT * FROM cohort_monthly UNION ALL SELECT * FROM cohort_quarterly UNION ALL SELECT * FROM cohort_yearly
)
ORDER BY g, c, f, p
