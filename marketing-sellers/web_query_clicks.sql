-- Hoja "Funnel WEB" — Clicks e inversión reportada, CO + MX, por granularidad
-- Source: papyrus-data{,-mx}.habi_wh_bi.resumen_inversiones_mkt_{co,mx} (canal_adquisicion='Web')
-- ⚠️ Cada país vive en un proyecto GCP distinto, misma forma de tabla.
-- Aquí las métricas SÍ son sumables (clicks/spend), pero se agregan por granularidad
-- para que el JSON tenga la misma forma que sessions y leads.

WITH base AS (
  SELECT 'MX' AS pais, date AS d, plataforma, spend, clicks
  FROM `papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx`
  WHERE canal_adquisicion = 'Web' AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY) AND date < CURRENT_DATE()
  UNION ALL
  SELECT 'CO', date, plataforma, spend, clicks
  FROM `papyrus-data.habi_wh_bi.resumen_inversiones_mkt_co`
  WHERE canal_adquisicion = 'Web' AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY) AND date < CURRENT_DATE()
),
expanded AS (
  SELECT b.pais, gran,
    CASE gran
      WHEN 'D' THEN b.d WHEN 'W' THEN DATE_TRUNC(b.d, ISOWEEK) WHEN 'C' THEN DATE_TRUNC(b.d, WEEK(WEDNESDAY))
      WHEN 'M' THEN DATE_TRUNC(b.d, MONTH) WHEN 'Q' THEN DATE_TRUNC(b.d, QUARTER) WHEN 'Y' THEN DATE_TRUNC(b.d, YEAR)
    END AS periodo,
    CASE
      WHEN LOWER(b.plataforma) LIKE '%google%' THEN 'Google'
      WHEN LOWER(b.plataforma) IN ('facebook','instagram','meta','fb','ig') THEN 'Meta'
      WHEN LOWER(b.plataforma) LIKE '%bing%' THEN 'Bing'
      WHEN LOWER(b.plataforma) LIKE '%tiktok%' THEN 'TikTok'
      ELSE 'Otro'
    END AS plataforma,
    b.spend, b.clicks
  FROM base b, UNNEST(['D','W','C','M','Q','Y']) AS gran
),
agg AS (
  SELECT pais, gran, periodo, plataforma,
         CAST(ROUND(SUM(spend), 0) AS INT64) AS spend,
         CAST(SUM(clicks) AS INT64) AS clicks
  FROM expanded GROUP BY 1,2,3,4
)
SELECT pais, gran, CASE gran
         WHEN 'M' THEN FORMAT_DATE('%Y-%m', periodo)
         WHEN 'Q' THEN CONCAT(FORMAT_DATE('%Y', periodo), '-Q', CAST(EXTRACT(QUARTER FROM periodo) AS STRING))
         WHEN 'Y' THEN FORMAT_DATE('%Y', periodo)
         ELSE CAST(periodo AS STRING)
       END AS periodo, plataforma, spend, clicks
FROM agg
QUALIFY DENSE_RANK() OVER (PARTITION BY pais, gran ORDER BY periodo DESC) <= 20
ORDER BY pais, gran, periodo, plataforma
