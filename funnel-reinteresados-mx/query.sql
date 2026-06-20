-- Campaña "reinteresados" (WEB, MX) — UNA FILA POR LEAD para filtrar geográficamente en el front.
-- Universo: utm_campaign de la campaña, fuente WEB (fuente_id=3), MX. 1 fila por NID.
-- Campos por lead:
--   estado_mx  = estado geográfico (estado_mexico) · area = área metropolitana
--   sid/slabel = estado ACTUAL del backbone · calif = alguna vez 20/63 · cita = alguna vez estado 27
--   asig = presente en WBR mart de asignados (mexico) · cierre = MM 'Cierre - Comprado'
--   contrato = Inmo 'Contrato firmado' · fc = fecha de creación (cohorte diaria)
WITH ea AS (
  SELECT deal_id, ARRAY_AGG(state_id ORDER BY date_create DESC, id DESC LIMIT 1)[OFFSET(0)] AS cur
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state` GROUP BY deal_id
),
ever AS (
  SELECT deal_id, MAX(IF(state_id IN (20,63),1,0)) AS ever_calif, MAX(IF(state_id=27,1,0)) AS ever_cita
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state` GROUP BY deal_id
),
mart AS (
  SELECT DISTINCT nid FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` WHERE pais='mexico'
)
SELECT
  COALESCE(NULLIF(TRIM(g.estado_mexico),''),'Sin dato')       AS estado_mx,
  COALESCE(NULLIF(TRIM(g.area_metropolitana),''),'Sin dato')  AS area,
  CAST(ea.cur AS STRING)                                      AS sid,
  COALESCE(st.label,'Sin estado')                             AS slabel,
  COALESCE(ev.ever_calif,0)                                   AS calif,
  COALESCE(ev.ever_cita,0)                                    AS cita,
  IF(m.nid IS NOT NULL,1,0)                                   AS asig,
  IF(g.oportunidad_del_negocio = "Cierre - Comprado",1,0)     AS cierre,
  IF(hd.oportunidad_inmobiliaria = "Contrato firmado",1,0)    AS contrato,
  CAST(CAST(g.fecha_creacion AS DATE) AS STRING)              AS fc
FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
JOIN `sellers-main-prod.hubspot.deals` hd ON hd.nid = g.nid AND hd.country = "México"
LEFT JOIN ea ON ea.deal_id = g.id_negocio
LEFT JOIN ever ev ON ev.deal_id = g.id_negocio
LEFT JOIN mart m ON m.nid = g.nid
LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_state` st ON st.id = ea.cur
WHERE hd.utm_campaign = "mex-sellers-paid-experiments-web-without-leads-retargeting-national-reinteresados"
  AND g.fuente_id = 3
QUALIFY ROW_NUMBER() OVER (PARTITION BY g.nid ORDER BY CAST(g.fecha_creacion AS DATE) DESC) = 1
