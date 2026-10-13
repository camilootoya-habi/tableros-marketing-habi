-- Inversión TOTAL de pauta de Habi MX (todas las plataformas y canales, incluida performance),
-- por día y plataforma, desde el arranque de la acción. Para el reporte "cuánto pesó la Rosa".
-- Fuente: la misma de okr-marketing y marketing-sellers. En USD (no hay columna de moneda; la
-- cuenta de Meta MX factura en USD y los CPC cuadran). Hoy se excluye: el día no está completo.
-- @desde lo pasa build.py (config.inicio_pagado).
SELECT
  CAST(date AS STRING) AS d,
  CASE
    WHEN LOWER(plataforma) LIKE '%google%' THEN 'Google'
    WHEN LOWER(plataforma) IN ('facebook', 'instagram', 'meta', 'fb', 'ig') THEN 'Meta'
    WHEN LOWER(plataforma) LIKE '%bing%' THEN 'Bing'
    WHEN LOWER(plataforma) LIKE '%tiktok%' THEN 'TikTok'
    ELSE 'Otro'
  END AS plataforma,
  ROUND(SUM(spend), 2) AS inversion
FROM `papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx`
WHERE date >= DATE(@desde) AND date < CURRENT_DATE()
GROUP BY 1, 2
ORDER BY 1, 2
