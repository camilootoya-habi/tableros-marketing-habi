-- Calidad de reinteresados vs WEB nuevo, en CUATRO ventanas: últimos 7 / 14 / 30 / 60 días.
-- La ventana filtra por FECHA DE CREACIÓN del lead (createdate); las etapas cuentan lo que le
-- pasó a esa gente, sin importar cuándo pasó. El tablero deja elegir la ventana porque cada
-- una responde algo distinto: a 7 días se ve la reacción reciente y el cierre todavía no
-- aparece (el ciclo de compra es más largo); a 60 días ya maduró y el cierre es comparable.
--
-- Cierre = las DOS líneas de negocio y hay que sumarlas:
--   · MM (compra directa): oportunidad_del_negocio = 'Cierre - Comprado'
--   · Inmobiliaria (red de aliados): la FECHA de firma, no la etapa —la etapa se mueve a
--     'Publicado'/'Captado' y borra la evidencia—. CO la guarda en fecha_captacion_inmobiliaria
--     y MX en fecha_de_contrato_firmado_mx; son disjuntas por país, así que basta un COALESCE.
WITH mart AS (
  SELECT DISTINCT nid, pais FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE pais IN ('mexico','colombia')
),
d AS (
  SELECT
    CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
    CASE WHEN utm_campaign LIKE '%reinteresados%' THEN 'Reinteresados' ELSE 'WEB nuevo' END AS cohorte,
    DATE_DIFF(CURRENT_DATE(), CAST(createdate AS DATE), DAY) AS antig,
    nid, country,
    IF(estado IN ('No gestionado','Sin pricing incial'),1,0) AS calif,
    IF(fecha_de_visita IS NOT NULL,1,0) AS cita,
    IF(oportunidad_del_negocio='Cierre - Comprado',1,0) AS cierre_mm,
    IF(COALESCE(fecha_captacion_inmobiliaria, fecha_de_contrato_firmado_mx) IS NOT NULL,1,0) AS cierre_inmo
  FROM `sellers-main-prod.hubspot.deals`
  -- La cohorte del loop la define su UTM, no la fuente (filtrar por fuente='WEB' dejaba fuera
  -- 419 leads propios de Web Scraping / Estudio Inmueble / Leadforms). El baseline sí es WEB.
  WHERE country IN ('México','Colombia')
    AND (utm_campaign LIKE '%reinteresados%' OR fuente='WEB')
    AND CAST(createdate AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
)
SELECT
  d.pais, d.cohorte, ventana,
  COUNT(*) AS leads,
  SUM(d.calif) AS calif_n,                       ROUND(AVG(d.calif)*100,1) AS calif_pct,
  SUM(IF(m.nid IS NOT NULL,1,0)) AS asignado_n,  ROUND(AVG(IF(m.nid IS NOT NULL,1,0))*100,1) AS asignado_pct,
  SUM(d.cita) AS cita_n,                         ROUND(AVG(d.cita)*100,1) AS cita_pct,
  SUM(d.cierre_mm) AS cierres_mm,
  SUM(d.cierre_inmo) AS cierres_inmo,
  SUM(d.cierre_mm) + SUM(d.cierre_inmo) AS cierres,
  ROUND(AVG(IF(d.cierre_mm=1 OR d.cierre_inmo=1,1,0))*100,2) AS cierre_pct
FROM d
CROSS JOIN UNNEST([7,14,30,60]) AS ventana
LEFT JOIN mart m ON m.nid=d.nid AND m.pais = CASE d.country WHEN 'México' THEN 'mexico' WHEN 'Colombia' THEN 'colombia' END
WHERE d.antig <= ventana
GROUP BY d.pais, d.cohorte, ventana
ORDER BY d.pais, d.cohorte, ventana
