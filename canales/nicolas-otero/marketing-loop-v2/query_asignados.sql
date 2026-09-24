-- Impacto de leads asignados por período — MX + CO — desde la WBR mart.
-- total_asignados = asignados de las 6 fuentes de marketing (fuente_id_tig); asignados_web = fuente WEB (3);
-- asignados_reint = subconjunto con utm_campaign LIKE %reinteresados% (leads del marketing loop). 1 fila por (tipo,pais,bucket).
WITH reint AS (
  SELECT DISTINCT nid FROM `sellers-main-prod.hubspot.deals`
  WHERE utm_campaign LIKE '%reinteresados%' AND country IN ('México','Colombia')
),
mart AS (
  SELECT DISTINCT nid, pais, dia, fuente_id_tig
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE dia >= DATE_SUB(CURRENT_DATE(), INTERVAL 20 MONTH)
    AND ((pais='mexico'   AND fuente_id_tig IN (3,7,35,39,46,47)) OR
         (pais='colombia' AND fuente_id_tig IN (3,7,20,35,39,47)))
),
joined AS (
  SELECT m.nid, m.pais, m.dia, m.fuente_id_tig, IF(r.nid IS NOT NULL,1,0) es_reint
  FROM mart m LEFT JOIN reint r ON r.nid=m.nid
)
SELECT 'dia' tipo, pais, CAST(dia AS STRING) bucket,
  COUNT(DISTINCT nid) total_asignados,
  COUNT(DISTINCT IF(fuente_id_tig=3,nid,NULL)) asignados_web,
  COUNT(DISTINCT IF(es_reint=1,nid,NULL)) asignados_reint
FROM joined GROUP BY pais,bucket
UNION ALL
SELECT 'semana' tipo, pais, CAST(DATE_TRUNC(dia,WEEK(MONDAY)) AS STRING) bucket,
  COUNT(DISTINCT nid) total_asignados, COUNT(DISTINCT IF(fuente_id_tig=3,nid,NULL)) asignados_web, COUNT(DISTINCT IF(es_reint=1,nid,NULL)) asignados_reint
FROM joined GROUP BY pais,bucket
UNION ALL
SELECT 'mes' tipo, pais, CAST(DATE_TRUNC(dia,MONTH) AS STRING) bucket,
  COUNT(DISTINCT nid) total_asignados, COUNT(DISTINCT IF(fuente_id_tig=3,nid,NULL)) asignados_web, COUNT(DISTINCT IF(es_reint=1,nid,NULL)) asignados_reint
FROM joined GROUP BY pais,bucket
ORDER BY tipo,pais,bucket
