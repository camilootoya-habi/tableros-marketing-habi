-- KPIs de cabecera del loop con tres ventanas acumuladas: MTD (mes en curso), WTD (semana
-- en curso, lunes→hoy) y YTD (año en curso). Solo la cohorte del loop (UTM reinteresados).
-- Cada métrica se cuenta por SU PROPIA fecha, que es lo único que hace comparables las
-- ventanas: los leads por createdate, las citas por fecha_de_visita y los cierres por
-- closedate. Contarlas todas por createdate mediría el reloj del lead, no el evento.
WITH d AS (
  SELECT
    CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
    nid,
    CAST(createdate AS DATE) AS f_creado,
    CAST(fecha_de_visita AS DATE) AS f_cita,
    IF(oportunidad_del_negocio='Cierre - Comprado', CAST(closedate AS DATE), NULL) AS f_cierre
  FROM `sellers-main-prod.hubspot.deals`
  WHERE country IN ('México','Colombia')
    AND fuente='WEB'
    AND utm_campaign LIKE '%reinteresados%'
    -- margen hacia atrás: un lead creado el año pasado puede tener su cita o su cierre ESTE año
    AND CAST(createdate AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 400 DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
)
SELECT
  pais,
  COUNTIF(f_creado >= DATE_TRUNC(CURRENT_DATE(), MONTH))        AS creados_mtd,
  COUNTIF(f_creado >= DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY))) AS creados_wtd,
  COUNTIF(f_creado >= DATE_TRUNC(CURRENT_DATE(), YEAR))         AS creados_ytd,
  COUNTIF(f_cita   >= DATE_TRUNC(CURRENT_DATE(), MONTH))        AS citas_mtd,
  COUNTIF(f_cita   >= DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY))) AS citas_wtd,
  COUNTIF(f_cita   >= DATE_TRUNC(CURRENT_DATE(), YEAR))         AS citas_ytd,
  COUNTIF(f_cierre >= DATE_TRUNC(CURRENT_DATE(), MONTH))        AS cierres_mtd,
  COUNTIF(f_cierre >= DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY))) AS cierres_wtd,
  COUNTIF(f_cierre >= DATE_TRUNC(CURRENT_DATE(), YEAR))         AS cierres_ytd
FROM d
GROUP BY pais
ORDER BY pais
