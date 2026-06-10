-- WBR 2.0 — Tráfico web (visitantes únicos) por bucket · CO · WEB-only
-- Fuente: Segment pages (eventos de pageview). Visitantes = COUNT(DISTINCT anonymous_id).
-- Emite (gran, bucket, visitantes) para los DOS cortes (week lun-dom · cycle mié-mar),
-- porque "únicos" no se puede re-bucketear sumando días → se calcula distinct por bucket en SQL.
WITH pv AS (
  SELECT anonymous_id, DATE(timestamp) AS d
  FROM `sellers-main-prod.co_segment_profiles.pages`
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
