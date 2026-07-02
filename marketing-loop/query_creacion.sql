-- Creación diaria de reinteresados + calificación, para vista "en vivo" y promedio móvil. MX + CO.
-- 1 fila por (pais, día de creación) desde el arranque del programa.
SELECT
  CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
  CAST(CAST(createdate AS DATE) AS STRING) AS fecha,
  COUNT(DISTINCT nid) AS creados,
  COUNT(DISTINCT IF(estado IN ('No gestionado','Sin pricing incial'), nid, NULL)) AS calificados
FROM `sellers-main-prod.hubspot.deals`
WHERE country IN ('México','Colombia') AND utm_campaign LIKE '%reinteresados%'
  AND CAST(createdate AS DATE) >= '2026-06-15'
GROUP BY pais, fecha
ORDER BY pais, fecha
