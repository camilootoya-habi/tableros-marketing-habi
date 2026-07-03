-- Leads creados HOY con UTM reinteresados, desde hubspot.deals (la fuente que refresca más rápido, ~7 min de lag).
-- "Hoy" en hora local de cada país. No requiere join a tabla_inmuebles_general (evita el lag de replicación).
SELECT 'MX' AS pais,
       COUNTIF(DATE(createdate,'America/Mexico_City')=CURRENT_DATE('America/Mexico_City')) AS creados_hoy
FROM `sellers-main-prod.hubspot.deals`
WHERE utm_campaign LIKE '%reinteresados%' AND country='México'
UNION ALL
SELECT 'CO' AS pais,
       COUNTIF(DATE(createdate,'America/Bogota')=CURRENT_DATE('America/Bogota')) AS creados_hoy
FROM `sellers-main-prod.hubspot.deals`
WHERE utm_campaign LIKE '%reinteresados%' AND country='Colombia'
