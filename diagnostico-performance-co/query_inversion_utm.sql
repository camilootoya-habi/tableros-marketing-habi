-- Inversión de performance CO atribuida por UTM (diccionario registro_unico_utm).
-- Match validado 2026-06-15: 100% del spend cruza por campana_original.
-- Granularidad diaria; el build agrega a semana ISO. Solo fuentes Paid de performance.
WITH dict AS (
  SELECT DISTINCT campana_mercadeo_original, mkt_channel_big, mkt_media
  FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
)
SELECT
  CAST(i.date AS STRING) AS dt,
  d.mkt_channel_big       AS fuente,   -- WEB | lead_forms | Estudio Inmueble
  ROUND(SUM(i.spend))       AS spend,
  ROUND(SUM(i.impressions)) AS impr,
  ROUND(SUM(i.clicks))      AS clicks
FROM `papyrus-data.habi_wh_bi.resumen_inversiones_mkt_co` i
LEFT JOIN dict d ON i.campana_original = d.campana_mercadeo_original
WHERE i.date >= '2025-01-01'
  AND i.date < CURRENT_DATE()
  AND d.mkt_media = 'Paid'
  AND d.mkt_channel_big IN ('WEB','lead_forms','Estudio Inmueble')
GROUP BY 1, 2
ORDER BY 1, 2
