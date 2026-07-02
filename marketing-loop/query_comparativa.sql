-- Comparación de CALIDAD: reinteresados vs leads WEB nuevos (baseline = fuente WEB sin UTM reinteresados). MX + CO.
-- Cohorte por createdate desde el arranque del programa. Métricas: calificado, asignado (WBR mart), cita, cierre.
WITH mart AS (
  SELECT DISTINCT nid, pais FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE pais IN ('mexico','colombia')
),
d AS (
  SELECT
    CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
    CASE WHEN utm_campaign LIKE '%reinteresados%' THEN 'Reinteresados' ELSE 'WEB nuevo' END AS cohorte,
    nid, country,
    IF(estado IN ('No gestionado','Sin pricing incial'),1,0) AS calif,
    IF(fecha_de_visita IS NOT NULL,1,0) AS cita,
    IF(oportunidad_del_negocio='Cierre - Comprado',1,0) AS cierre
  FROM `sellers-main-prod.hubspot.deals`
  WHERE country IN ('México','Colombia') AND fuente='WEB'
    AND CAST(createdate AS DATE) >= '2026-06-15'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
)
SELECT
  d.pais, d.cohorte,
  COUNT(*) AS leads,
  ROUND(AVG(d.calif)*100,1) AS calif_pct,
  ROUND(AVG(IF(m.nid IS NOT NULL,1,0))*100,1) AS asignado_pct,
  ROUND(AVG(d.cita)*100,1) AS cita_pct,
  ROUND(AVG(d.cierre)*100,2) AS cierre_pct
FROM d
LEFT JOIN mart m ON m.nid=d.nid AND m.pais = CASE d.country WHEN 'México' THEN 'mexico' WHEN 'Colombia' THEN 'colombia' END
GROUP BY d.pais, d.cohorte
ORDER BY d.pais, d.cohorte
