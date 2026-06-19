-- Funnel + antifunnel + evolución diaria de la campaña de retargeting "reinteresados" (WEB, MX).
-- Universo: utm_campaign de la campaña, fuente WEB (fuente_id=3), MX.
-- Emite dos tipos de fila (col `kind`):
--   'estado' = breakdown por estado ACTUAL (funnel: 20/63 = Calificado · resto = Antifunnel).
--   'diario' = cohorte por fecha de creación: registros (NIDs) y calificados (estado 20/63) por día.
WITH ea AS (
  SELECT deal_id, ARRAY_AGG(state_id ORDER BY date_create DESC, id DESC LIMIT 1)[OFFSET(0)] AS sid
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
  GROUP BY deal_id
),
base AS (
  SELECT g.nid, ea.sid, CAST(g.fecha_creacion AS DATE) AS fc
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
  JOIN `sellers-main-prod.hubspot.deals` hd
    ON hd.nid = g.nid AND hd.country = "México"
  LEFT JOIN ea ON ea.deal_id = g.id_negocio
  WHERE hd.utm_campaign = "mex-sellers-paid-experiments-web-without-leads-retargeting-national-reinteresados"
    AND g.fuente_id = 3
  QUALIFY ROW_NUMBER() OVER (PARTITION BY g.nid ORDER BY CAST(g.fecha_creacion AS DATE) DESC) = 1
)
SELECT 'estado' AS kind,
       IF(b.sid IN (20,63), "Calificado", "Antifunnel") AS grupo,
       CAST(b.sid AS STRING) AS state_id,
       COALESCE(st.label, "Sin estado") AS label,
       CAST(NULL AS STRING) AS fecha,
       COUNT(*) AS n, 0 AS n_calif
FROM base b
LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_state` st ON st.id = b.sid
GROUP BY 1,2,3,4
UNION ALL
SELECT 'diario' AS kind, NULL, NULL, NULL,
       CAST(fc AS STRING) AS fecha,
       COUNT(*) AS n, COUNTIF(sid IN (20,63)) AS n_calif
FROM base
GROUP BY fc
ORDER BY kind, fecha, n DESC
