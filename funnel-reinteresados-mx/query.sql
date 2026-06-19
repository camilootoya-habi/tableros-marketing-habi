-- Funnel + antifunnel + evolución diaria de la campaña "reinteresados" (WEB, MX),
-- con corte por ASIGNACIÓN en el WBR mart de asignados (pais='mexico').
-- Universo: utm_campaign de la campaña, fuente WEB (fuente_id=3), MX.
-- Filas (col `kind`):
--   'estado' = breakdown por estado ACTUAL; n = total, n_asig = asignados (resto = no asignados).
--              grupo: 20/63 = Calificado · resto = Antifunnel.
--   'diario' = cohorte por fecha de creación; n = registros, n_calif = calificados (20/63).
WITH ea AS (
  SELECT deal_id, ARRAY_AGG(state_id ORDER BY date_create DESC, id DESC LIMIT 1)[OFFSET(0)] AS sid
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
  GROUP BY deal_id
),
mart AS (
  SELECT DISTINCT nid
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE pais = 'mexico'
),
base AS (
  SELECT g.nid, ea.sid, CAST(g.fecha_creacion AS DATE) AS fc,
         IF(m.nid IS NOT NULL, 1, 0) AS asignado
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
  JOIN `sellers-main-prod.hubspot.deals` hd
    ON hd.nid = g.nid AND hd.country = "México"
  LEFT JOIN ea ON ea.deal_id = g.id_negocio
  LEFT JOIN mart m ON m.nid = g.nid
  WHERE hd.utm_campaign = "mex-sellers-paid-experiments-web-without-leads-retargeting-national-reinteresados"
    AND g.fuente_id = 3
  QUALIFY ROW_NUMBER() OVER (PARTITION BY g.nid ORDER BY CAST(g.fecha_creacion AS DATE) DESC) = 1
)
SELECT 'estado' AS kind,
       IF(b.sid IN (20,63), "Calificado", "Antifunnel") AS grupo,
       CAST(b.sid AS STRING) AS state_id,
       COALESCE(st.label, "Sin estado") AS label,
       CAST(NULL AS STRING) AS fecha,
       COUNT(*) AS n, COUNTIF(b.asignado = 1) AS n_asig, 0 AS n_calif
FROM base b
LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_state` st ON st.id = b.sid
GROUP BY 1,2,3,4
UNION ALL
SELECT 'diario' AS kind, NULL, NULL, NULL,
       CAST(fc AS STRING) AS fecha,
       COUNT(*) AS n, 0 AS n_asig, COUNTIF(sid IN (20,63)) AS n_calif
FROM base
GROUP BY fc
ORDER BY kind, fecha, n DESC
