-- Leads recreados (UTM reinteresados) con su fecha de creación y si calificaron (Market Maker 20/63). MX + CO.
-- Se usa para enlazar creado/calificado a la cosecha de envío (por nid original vía ledger).
SELECT
  CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
  nid,
  CAST(CAST(createdate AS DATE) AS STRING) AS fecha_creacion,
  IF(estado IN ('No gestionado','Sin pricing incial'), 1, 0) AS calif
FROM `sellers-main-prod.hubspot.deals`
WHERE utm_campaign LIKE '%reinteresados%' AND country IN ('México','Colombia')
QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
