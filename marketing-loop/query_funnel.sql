-- Funnel de reactivación de reinteresados (los recreados con UTM reinteresados), MX + CO.
-- Recreados (en hubspot) -> Calificado (MM 20/63) -> Asignado (WBR mart) -> Cita -> Cierre.
WITH mart AS (
  SELECT DISTINCT nid, pais FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE pais IN ('mexico','colombia')
),
d AS (
  SELECT
    CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
    nid, country,
    IF(estado IN ('No gestionado','Sin pricing incial'),1,0) AS calif,
    IF(fecha_de_visita IS NOT NULL,1,0) AS cita,
    -- Cierre = las DOS líneas. oportunidad_del_negocio es SOLO Market Maker (compra directa);
    -- la inmobiliaria (una CAPTACION, no una venta) se detecta por su FECHA y no por la etapa,
    -- que se mueve y borra la evidencia de la firma. Campos disjuntos por país -> COALESCE.
    IF(oportunidad_del_negocio='Cierre - Comprado',1,0) AS cierre_mm,
    IF(COALESCE(fecha_captacion_inmobiliaria, fecha_de_contrato_firmado_mx) IS NOT NULL,1,0) AS cierre_inmo
  FROM `sellers-main-prod.hubspot.deals`
  WHERE country IN ('México','Colombia') AND utm_campaign LIKE '%reinteresados%'
    AND CAST(createdate AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)   -- solo leads creados en los últimos 14 días
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
)
SELECT
  d.pais,
  COUNT(*) AS recreados,
  SUM(d.calif) AS calificados,
  SUM(IF(m.nid IS NOT NULL,1,0)) AS asignados,
  SUM(d.cita) AS citas,
  SUM(d.cierre_mm) AS cierres_mm,
  SUM(d.cierre_inmo) AS cierres_inmo,
  SUM(d.cierre_mm) + SUM(d.cierre_inmo) AS cierres
FROM d
LEFT JOIN mart m ON m.nid=d.nid AND m.pais = CASE d.country WHEN 'México' THEN 'mexico' WHEN 'Colombia' THEN 'colombia' END
GROUP BY d.pais ORDER BY d.pais
