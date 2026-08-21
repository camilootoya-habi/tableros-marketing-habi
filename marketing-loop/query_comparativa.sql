-- Comparación de CALIDAD: reinteresados vs leads WEB nuevos (baseline = fuente WEB sin UTM reinteresados). MX + CO.
-- DOS ventanas a propósito (2026-08-21):
--   · Calificado / Asignado / Cita: cohorte de los ÚLTIMOS 14 DÍAS. Son eventos tempranos y
--     con 14 días ya se ven.
--   · Cierre: cohorte MADURA de 31-90 días. Con 14 días el cierre daba 0.0 SIEMPRE en las dos
--     cohortes — no porque el dato faltara, sino porque el ciclo de compra es más largo que la
--     ventana (verificado: reinteresados 31-90d cierra 0.65% CO / 0.5% MX, y WEB nuevo madura
--     hasta 1.49% a >180d). Medir cierre a 14 días es medir el reloj, no el negocio.
WITH mart AS (
  SELECT DISTINCT nid, pais FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE pais IN ('mexico','colombia')
),
d AS (
  SELECT
    CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
    CASE WHEN utm_campaign LIKE '%reinteresados%' THEN 'Reinteresados' ELSE 'WEB nuevo' END AS cohorte,
    nid, country,
    DATE_DIFF(CURRENT_DATE(), CAST(createdate AS DATE), DAY) AS antiguedad,
    IF(estado IN ('No gestionado','Sin pricing incial'),1,0) AS calif,
    IF(fecha_de_visita IS NOT NULL,1,0) AS cita,
    IF(oportunidad_del_negocio='Cierre - Comprado',1,0) AS cierre
  FROM `sellers-main-prod.hubspot.deals`
  WHERE country IN ('México','Colombia') AND fuente='WEB'
    AND CAST(createdate AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
)
SELECT
  d.pais, d.cohorte,
  COUNTIF(d.antiguedad <= 14) AS leads,
  -- conteos absolutos además del %: un 58,7% sobre 172 leads y sobre 2.947 no se leen igual
  COUNTIF(d.antiguedad <= 14 AND d.calif = 1) AS calif_n,
  COUNTIF(d.antiguedad <= 14 AND m.nid IS NOT NULL) AS asignado_n,
  COUNTIF(d.antiguedad <= 14 AND d.cita = 1) AS cita_n,
  ROUND(AVG(IF(d.antiguedad <= 14, d.calif, NULL))*100,1) AS calif_pct,
  ROUND(AVG(IF(d.antiguedad <= 14, IF(m.nid IS NOT NULL,1,0), NULL))*100,1) AS asignado_pct,
  ROUND(AVG(IF(d.antiguedad <= 14, d.cita, NULL))*100,1) AS cita_pct,
  -- cohorte madura para cierre
  COUNTIF(d.antiguedad BETWEEN 31 AND 90) AS leads_maduros,
  SUM(IF(d.antiguedad BETWEEN 31 AND 90, d.cierre, 0)) AS cierres,
  ROUND(AVG(IF(d.antiguedad BETWEEN 31 AND 90, d.cierre, NULL))*100,2) AS cierre_pct
FROM d
LEFT JOIN mart m ON m.nid=d.nid AND m.pais = CASE d.country WHEN 'México' THEN 'mexico' WHEN 'Colombia' THEN 'colombia' END
GROUP BY d.pais, d.cohorte
ORDER BY d.pais, d.cohorte
