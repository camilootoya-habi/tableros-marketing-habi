-- Funnel Web MX — Sesiones + form page steps (etapas 2-11)
-- Source: sellers-main-prod.mx_segment_profiles.pages
-- Atribución: primer page event del anonymous_id en la semana define utm + device

WITH evs AS (
  SELECT
    anonymous_id,
    DATE_TRUNC(DATE(timestamp, 'America/Mexico_City'), ISOWEEK) AS week,
    timestamp AS ts,
    context_page_path AS path,
    LOWER(IFNULL(context_campaign_utm_source, '')) AS utm_source,
    LOWER(IFNULL(context_campaign_utm_medium, '')) AS utm_medium,
    context_user_agent_data_mobile AS is_mobile,
    LOWER(IFNULL(context_user_agent_data_platform, '')) AS ua_platform
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Mexico_City') >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK)
    AND DATE(timestamp, 'America/Mexico_City') < DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
    AND context_page_url LIKE '%habi.mx%'
    AND anonymous_id IS NOT NULL
),
first_event AS (
  SELECT
    anonymous_id, week,
    ARRAY_AGG(STRUCT(utm_source, utm_medium, is_mobile, ua_platform) ORDER BY ts LIMIT 1)[OFFSET(0)] AS fe
  FROM evs
  GROUP BY 1, 2
),
attr AS (
  SELECT
    anonymous_id, week,
    CASE
      WHEN fe.utm_source LIKE '%google%' AND fe.utm_medium IN ('cpc','paid','ppc','paidsearch') THEN 'Google/Paid'
      WHEN fe.utm_source LIKE '%google%' THEN 'Google/Organic'
      WHEN fe.utm_source IN ('facebook','instagram','meta','fb','ig') AND fe.utm_medium IN ('cpc','paid','ppc','paid_social','paidsocial') THEN 'Meta/Paid'
      WHEN fe.utm_source IN ('facebook','instagram','meta','fb','ig') THEN 'Meta/Organic'
      WHEN fe.utm_source LIKE '%bing%' THEN 'Bing/Paid'
      WHEN fe.utm_source LIKE '%tiktok%' THEN 'TikTok/Paid'
      WHEN fe.utm_source = '' THEN 'Direct/Direct'
      ELSE 'Otro/Otro'
    END AS canal_plat,
    CASE
      WHEN fe.is_mobile = TRUE AND fe.ua_platform LIKE '%ipad%' THEN 'tablet'
      WHEN fe.is_mobile = TRUE THEN 'mobile'
      WHEN fe.is_mobile = FALSE THEN 'desktop'
      ELSE 'unknown'
    END AS device
  FROM first_event
),
visits AS (
  SELECT e.anonymous_id, e.week, e.path, a.canal_plat, a.device
  FROM evs e
  JOIN attr a USING (anonymous_id, week)
),
stage_visits AS (
  SELECT
    week,
    CASE path
      WHEN '/formulario-inmueble/inicio' THEN 'inicio'
      WHEN '/formulario-inmueble/inmuebles-zona' THEN 'zona'
      WHEN '/formulario-inmueble/confirmar-ubicacion-mx' THEN 'confirmar_ubicacion'
      WHEN '/formulario-inmueble/datos-inmueble' THEN 'datos_inmueble'
      WHEN '/formulario-inmueble/caracteristicas' THEN 'caracteristicas'
      WHEN '/formulario-inmueble/ultimos-detalles' THEN 'ultimos_detalles'
      WHEN '/formulario-inmueble/sugerencias-de-propiedades' THEN 'sugerencias'
      WHEN '/formulario-inmueble/editar-sugerencias' THEN 'sugerencias'
      WHEN '/formulario-inmueble/contacto' THEN 'contacto'
      WHEN '/formulario-inmueble/felicitaciones' THEN 'felicitaciones'
      ELSE NULL
    END AS stage,
    canal_plat, device, anonymous_id
  FROM visits
),
agg_stages AS (
  SELECT CAST(week AS STRING) AS week_start, stage, canal_plat, device, COUNT(DISTINCT anonymous_id) AS n_visitors
  FROM stage_visits
  WHERE stage IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
agg_session AS (
  SELECT CAST(week AS STRING) AS week_start, 'session' AS stage, canal_plat, device, COUNT(DISTINCT anonymous_id) AS n_visitors
  FROM visits
  GROUP BY 1, 3, 4
)
SELECT * FROM agg_stages
UNION ALL
SELECT * FROM agg_session
ORDER BY week_start, stage, canal_plat, device
