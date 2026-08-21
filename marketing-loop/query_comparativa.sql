-- Calidad de reinteresados vs WEB nuevo, DESGLOSADA POR COHORTE DE CREACIÓN.
--
-- Una sola ventana siempre miente en alguna etapa: a 14 días el cierre da 0 % porque el
-- ciclo de compra no cabe ahí, y a 90 días el "calificado" ya no dice nada de lo que está
-- pasando esta semana. Por eso el funnel se abre por antigüedad del lead: cada fila es una
-- cohorte con las cuatro etapas sobre SU propia base, y la maduración se lee hacia abajo.
--
-- Cada cohorte es un grupo de leads por su fecha de creación; las etapas cuentan lo que le
-- pasó a ESA gente, sin importar cuándo pasó. Eso las hace distintas de los KPIs de
-- cabecera, que cuentan eventos ocurridos en el mes / la semana / el año.
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
    -- OJO: cierre = iBuyer (este campo) + Inmobiliaria (oportunidad_inmobiliaria). Ver marketing-loop/METRICAS.md
    -- DOS líneas de negocio: Market Maker (compra directa) e Inmobiliaria (red de aliados).
    -- oportunidad_del_negocio es SOLO el campo de Market Maker; el mundo inmobiliaria vive
    -- en oportunidad_inmobiliaria y antes se perdía entero.
    IF(oportunidad_del_negocio='Cierre - Comprado',1,0) AS cierre_mm,
    IF(oportunidad_inmobiliaria='Contrato firmado',1,0) AS cierre_inmo
  FROM `sellers-main-prod.hubspot.deals`
  -- La cohorte del loop la define su UTM, no la fuente: filtrar por fuente='WEB' dejaba
  -- fuera 419 leads propios. El baseline sí es WEB (leads nuevos del sitio sin esa UTM).
  WHERE country IN ('México','Colombia')
    AND (utm_campaign LIKE '%reinteresados%' OR fuente='WEB')
    AND CAST(createdate AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
)
SELECT
  d.pais, d.cohorte,
  CASE WHEN d.antig <= 14 THEN '1'
       WHEN d.antig <= 30 THEN '2'
       WHEN d.antig <= 90 THEN '3'
       WHEN d.antig <= 180 THEN '4'
       ELSE '5' END AS orden,
  CASE WHEN d.antig <= 14 THEN '0-14 días'
       WHEN d.antig <= 30 THEN '15-30 días'
       WHEN d.antig <= 90 THEN '31-90 días'
       WHEN d.antig <= 180 THEN '91-180 días'
       ELSE 'más de 180 días' END AS edad,
  COUNT(*) AS leads,
  SUM(d.calif) AS calif_n,                                  ROUND(AVG(d.calif)*100,1) AS calif_pct,
  SUM(IF(m.nid IS NOT NULL,1,0)) AS asignado_n,             ROUND(AVG(IF(m.nid IS NOT NULL,1,0))*100,1) AS asignado_pct,
  SUM(d.cita) AS cita_n,                                    ROUND(AVG(d.cita)*100,1) AS cita_pct,
  SUM(d.cierre_mm) AS cierres_mm,                           ROUND(AVG(d.cierre_mm)*100,2) AS cierre_mm_pct,
  SUM(d.cierre_inmo) AS cierres_inmo,                       ROUND(AVG(d.cierre_inmo)*100,2) AS cierre_inmo_pct,
  SUM(d.cierre_mm) + SUM(d.cierre_inmo) AS cierres,
  ROUND(AVG(IF(d.cierre_mm=1 OR d.cierre_inmo=1,1,0))*100,2) AS cierre_pct
FROM d
LEFT JOIN mart m ON m.nid=d.nid AND m.pais = CASE d.country WHEN 'México' THEN 'mexico' WHEN 'Colombia' THEN 'colombia' END
GROUP BY d.pais, d.cohorte, orden, edad
ORDER BY d.pais, d.cohorte, orden
