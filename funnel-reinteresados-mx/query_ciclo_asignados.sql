-- Impacto de leads asignados por ciclo comercial (semana WBR) — MX + CO.
-- total_asignados = todos los asignados de marketing (todas las fuentes) del ciclo, desde la WBR mart.
-- asignados_reint = subconjunto cuyo nid tiene UTM de reinteresados (hubspot.deals).
-- El ratio (reint/total) se calcula en el cliente. 1 fila por (pais, ciclo).
WITH reint AS (
  SELECT DISTINCT nid FROM `sellers-main-prod.hubspot.deals`
  WHERE utm_campaign LIKE '%reinteresados%' AND country IN ('México','Colombia')
),
mart AS (
  SELECT DISTINCT nid, pais, semana
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE pais IN ('mexico','colombia')
    -- solo las 6 fuentes de marketing (se excluye 'Otro'), para cuadrar con los demás tableros
    AND fuente IN ('WEB','Ventanas','Leadform','Broker','Habimetro','CRM')
    AND semana >= DATE_SUB(CURRENT_DATE(), INTERVAL 16 WEEK)
)
SELECT
  m.pais,
  CAST(m.semana AS STRING) AS ciclo,
  COUNT(DISTINCT m.nid) AS total_asignados,
  COUNT(DISTINCT IF(r.nid IS NOT NULL, m.nid, NULL)) AS asignados_reint
FROM mart m
LEFT JOIN reint r ON r.nid = m.nid
GROUP BY m.pais, ciclo
ORDER BY m.pais, ciclo
