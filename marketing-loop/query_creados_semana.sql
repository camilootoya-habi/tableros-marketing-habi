-- Leads del loop CREADOS en los últimos 7 días, por país. Fuente: hubspot.deals por UTM
-- (misma definición que el resto del tablero) y no la tabla `recreation` de Neon, que no
-- captura las creaciones del repo viejo.
SELECT
  CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
  COUNT(DISTINCT nid) AS creados
FROM `sellers-main-prod.hubspot.deals`
WHERE country IN ('México','Colombia')
  AND fuente='WEB'
  AND utm_campaign LIKE '%reinteresados%'
  AND CAST(createdate AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY 1
