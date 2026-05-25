-- Funnel Web MX — Clicks reportados (etapa 1)
-- Source: papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx (canal_adquisicion='Web')

WITH base AS (
  SELECT
    DATE_TRUNC(date, ISOWEEK) AS week,
    CASE
      WHEN LOWER(plataforma) LIKE '%google%' THEN 'Google'
      WHEN LOWER(plataforma) IN ('facebook', 'instagram', 'meta', 'fb', 'ig') THEN 'Meta'
      WHEN LOWER(plataforma) LIKE '%bing%' THEN 'Bing'
      WHEN LOWER(plataforma) LIKE '%tiktok%' THEN 'TikTok'
      ELSE 'Otro'
    END AS plataforma_norm,
    spend,
    clicks,
    impressions
  FROM `papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx`
  WHERE canal_adquisicion = 'Web'
    AND date >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK)
    AND date < DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
)
SELECT
  CAST(week AS STRING) AS week_start,
  plataforma_norm AS plataforma,
  CAST(ROUND(SUM(spend), 0) AS INT64) AS spend,
  CAST(SUM(clicks) AS INT64) AS clicks,
  CAST(SUM(impressions) AS INT64) AS impressions
FROM base
GROUP BY 1, 2
ORDER BY 1, 2
