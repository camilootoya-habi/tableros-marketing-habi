-- KPIs de cabecera del loop en MTD (mes en curso), WTD (semana, lunes→hoy) y YTD (año).
--
-- DOS LÍNEAS DE NEGOCIO, no una (corregido 2026-08-21):
--   · Market Maker / compra directa  -> oportunidad_del_negocio = 'Cierre - Comprado', por closedate
--   · Inmobiliaria / red de aliados  -> oportunidad_inmobiliaria = 'Contrato firmado',  por fecha_captacion_inmobiliaria
-- Antes solo se contaba la primera y se perdía TODA la línea inmobiliaria: son 29 contratos
-- firmados del loop contra 18 compras directas, o sea que faltaba el 62 % de los cierres.
-- `fecha_de_firma` no sirve para fechar: está vacía en toda la tabla.
--
-- POBLACIÓN sin filtro de fuente: la UTM del loop ya identifica la cohorte, y filtrar por
-- fuente='WEB' dejaba fuera 419 leads propios (Web Scraping, Estudio Inmueble, Leadforms).
WITH d AS (
  SELECT
    CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
    nid,
    CAST(createdate AS DATE) AS f_creado,
    CAST(fecha_de_visita AS DATE) AS f_cita,
    IF(oportunidad_del_negocio='Cierre - Comprado', CAST(closedate AS DATE), NULL) AS f_cierre_mm,
    IF(oportunidad_inmobiliaria='Contrato firmado', CAST(fecha_captacion_inmobiliaria AS DATE), NULL) AS f_cierre_inmo
  FROM `sellers-main-prod.hubspot.deals`
  WHERE country IN ('México','Colombia')
    AND utm_campaign LIKE '%reinteresados%'
    -- margen: un lead creado el año pasado puede tener su cita o su cierre ESTE año
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
  COUNTIF(f_cierre_mm >= DATE_TRUNC(CURRENT_DATE(), MONTH))        AS cierres_mm_mtd,
  COUNTIF(f_cierre_mm >= DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY))) AS cierres_mm_wtd,
  COUNTIF(f_cierre_mm >= DATE_TRUNC(CURRENT_DATE(), YEAR))         AS cierres_mm_ytd,
  COUNTIF(f_cierre_inmo >= DATE_TRUNC(CURRENT_DATE(), MONTH))        AS cierres_inmo_mtd,
  COUNTIF(f_cierre_inmo >= DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY))) AS cierres_inmo_wtd,
  COUNTIF(f_cierre_inmo >= DATE_TRUNC(CURRENT_DATE(), YEAR))         AS cierres_inmo_ytd,
  COUNTIF(f_cierre_mm >= DATE_TRUNC(CURRENT_DATE(), MONTH))
    + COUNTIF(f_cierre_inmo >= DATE_TRUNC(CURRENT_DATE(), MONTH))        AS cierres_mtd,
  COUNTIF(f_cierre_mm >= DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY)))
    + COUNTIF(f_cierre_inmo >= DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY))) AS cierres_wtd,
  COUNTIF(f_cierre_mm >= DATE_TRUNC(CURRENT_DATE(), YEAR))
    + COUNTIF(f_cierre_inmo >= DATE_TRUNC(CURRENT_DATE(), YEAR))         AS cierres_ytd
FROM d
GROUP BY pais
ORDER BY pais
