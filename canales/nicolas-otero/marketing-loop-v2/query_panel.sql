-- Citas y cierres del loop en los rangos del panel (hoy / 7 / 30 / 90 días), por país.
-- Cada métrica por SU fecha: citas por fecha_de_visita, cierres por la fecha de cierre de su
-- línea (compra directa = closedate; inmobiliaria = la fecha de firma, disjunta por país).
WITH d AS (
  SELECT
    CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
    nid,
    CAST(fecha_de_visita AS DATE) AS f_cita,
    IF(oportunidad_del_negocio='Cierre - Comprado', CAST(closedate AS DATE), NULL) AS f_mm,
    CAST(COALESCE(fecha_captacion_inmobiliaria, fecha_de_contrato_firmado_mx) AS DATE) AS f_inmo
  FROM `sellers-main-prod.hubspot.deals`
  WHERE country IN ('México','Colombia') AND utm_campaign LIKE '%reinteresados%'
    AND CAST(createdate AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 400 DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
),
r AS (SELECT * FROM UNNEST([0,7,30,90]) AS dias)
-- Cada rango es una ventana de (dias+1) días que termina hoy. *_prev = la ventana contigua
-- del mismo largo justo antes (hoy vs ayer, 7 → los 8 días previos, ...), para el comparativo.
SELECT
  d.pais, r.dias,
  COUNTIF(d.f_cita >= DATE_SUB(CURRENT_DATE(), INTERVAL r.dias DAY)) AS citas,
  COUNTIF(d.f_mm   >= DATE_SUB(CURRENT_DATE(), INTERVAL r.dias DAY)) AS cierres_mm,
  COUNTIF(d.f_inmo >= DATE_SUB(CURRENT_DATE(), INTERVAL r.dias DAY)) AS cierres_inmo,
  COUNTIF(d.f_cita BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 2*r.dias+1 DAY) AND DATE_SUB(CURRENT_DATE(), INTERVAL r.dias+1 DAY)) AS citas_prev,
  COUNTIF(d.f_mm   BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 2*r.dias+1 DAY) AND DATE_SUB(CURRENT_DATE(), INTERVAL r.dias+1 DAY)) AS cierres_mm_prev,
  COUNTIF(d.f_inmo BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 2*r.dias+1 DAY) AND DATE_SUB(CURRENT_DATE(), INTERVAL r.dias+1 DAY)) AS cierres_inmo_prev
FROM d CROSS JOIN r
GROUP BY d.pais, r.dias
ORDER BY d.pais, r.dias
