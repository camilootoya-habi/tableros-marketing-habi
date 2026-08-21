-- Cierres de la SEMANA de la cohorte del loop (UTM reinteresados), por país.
-- Se cuentan por `closedate` (fecha en que el negocio se cerró), NO por createdate: un lead
-- creado esta semana no alcanza a cerrarse esta semana. `fecha_de_firma` está vacía en toda
-- la tabla (verificado 21-ago-26: 0 de 3.287 cierres la traen), por eso closedate.
SELECT
  CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
  COUNT(*) AS cierres
FROM `sellers-main-prod.hubspot.deals`
WHERE country IN ('México','Colombia')
  AND fuente='WEB'
  AND utm_campaign LIKE '%reinteresados%'
  -- OJO: cierre = iBuyer (este campo) + Inmobiliaria (oportunidad_inmobiliaria). Ver marketing-loop/METRICAS.md
  AND oportunidad_del_negocio='Cierre - Comprado'
  AND CAST(closedate AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY 1
