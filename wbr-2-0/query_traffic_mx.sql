-- WBR 2.0 — Tráfico web (visitantes únicos) por bucket · MX · WEB-only
-- Fuente: Segment pages MX. Ver query_traffic.sql (CO) para notas.
WITH pv AS (
  SELECT anonymous_id, DATE(timestamp) AS d
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
    AND DATE(timestamp) < CURRENT_DATE()
    AND anonymous_id IS NOT NULL
)
SELECT 'week' AS gran,
  CAST(DATE_TRUNC(d, ISOWEEK) AS STRING) AS bucket,
  COUNT(DISTINCT anonymous_id) AS visitantes
FROM pv GROUP BY 2
UNION ALL
SELECT 'cycle' AS gran,
  CAST(DATE_SUB(d, INTERVAL MOD(EXTRACT(DAYOFWEEK FROM d) - 4 + 7, 7) DAY) AS STRING) AS bucket,
  COUNT(DISTINCT anonymous_id) AS visitantes
FROM pv GROUP BY 2
ORDER BY gran, bucket
