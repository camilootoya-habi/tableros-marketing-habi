-- Campaña "reinteresados" (WEB) — MX y CO, 1 fila por lead, para selector de país + filtro geo en el front.
-- MX: utm 'mex-sellers-...-reinteresados' · CO: utm 'col-sellers-...-reinteresados'. Fuente WEB (fuente_id=3).
-- Columnas: pais · geo (MX=estado_mexico / CO=ciudad) · area (metropolitana) · sid/slabel (estado ACTUAL)
--   · calif (MM: alguna vez 20/63) · calif_inmo (Inmo: alguna vez state 20 en history_state_real_estate)
--   · cita (alguna vez 27) · gabi (GABI disparado = product_qualified no nulo) · owner (deal con hubspot_owner_id)
--   · asig (WBR mart) · cierre (MM 'Cierre - Comprado') · contrato (Inmo 'Contrato firmado') · fc (fecha creación).
-- Nota asignación: el funnel distingue 2 hitos. "Asignados (GABI)" = product_qualified NO nulo en el negocio
--   (MX: mx_rds_staging.habi_db_property_deal · CO: co_rds_staging.habi_db_tabla_negocio_inmueble) → GABI ya
--   está gestionando comercialmente el lead. "Asignados (WBR Mart)" = lead presente en el WBR mart (downstream,
--   llega con rezago). GABI puede dispararse sin que el lead aún figure en el mart.
WITH
mart AS (
  SELECT DISTINCT nid, pais FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
),
-- product_qualified (GABI disparado) por nid, por país
pq_mx AS (
  SELECT nid, MAX(IF(product_qualified IS NOT NULL,1,0)) gabi
  FROM `sellers-main-prod.mx_rds_staging.habi_db_property_deal` GROUP BY nid
),
pq_co AS (
  SELECT nid, MAX(IF(product_qualified IS NOT NULL,1,0)) gabi
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` GROUP BY nid
),
-- calificado Inmo = alguna vez state_id=20 en el funnel Inmobiliaria (history_state_real_estate), por deal_id
inmo_mx AS (
  SELECT deal_id, MAX(IF(state_id=20,1,0)) ever_calif_inmo
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state_real_estate` GROUP BY deal_id
),
inmo_co AS (
  SELECT deal_id, MAX(IF(state_id=20,1,0)) ever_calif_inmo
  FROM `sellers-main-prod.co_rds_staging.habi_db_history_state_real_estate` GROUP BY deal_id
),
-- ===== MÉXICO =====
ea_mx AS (
  SELECT deal_id, ARRAY_AGG(state_id ORDER BY date_create DESC, id DESC LIMIT 1)[OFFSET(0)] AS cur
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state` GROUP BY deal_id
),
ever_mx AS (
  SELECT deal_id, MAX(IF(state_id IN (20,63),1,0)) ever_calif, MAX(IF(state_id=27,1,0)) ever_cita
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state` GROUP BY deal_id
),
mx AS (
  SELECT 'MX' AS pais,
    COALESCE(NULLIF(TRIM(g.estado_mexico),''),'Sin dato') AS geo,
    COALESCE(NULLIF(TRIM(g.area_metropolitana),''),'Sin dato') AS area,
    CAST(ea.cur AS STRING) AS sid, COALESCE(st.label,'Sin estado') AS slabel,
    COALESCE(ev.ever_calif,0) AS calif, COALESCE(im.ever_calif_inmo,0) AS calif_inmo,
    COALESCE(ev.ever_cita,0) AS cita,
    COALESCE(pq.gabi,0) AS gabi,
    IF(hd.hubspot_owner_id IS NOT NULL AND hd.hubspot_owner_id != '',1,0) AS owner,
    IF(m.nid IS NOT NULL,1,0) AS asig,
    IF(g.oportunidad_del_negocio='Cierre - Comprado',1,0) AS cierre,
    IF(hd.oportunidad_inmobiliaria='Contrato firmado',1,0) AS contrato,
    CAST(CAST(g.fecha_creacion AS DATE) AS STRING) AS fc
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
  JOIN `sellers-main-prod.hubspot.deals` hd ON hd.nid=g.nid AND hd.country='México'
  LEFT JOIN ea_mx ea ON ea.deal_id=g.id_negocio
  LEFT JOIN ever_mx ev ON ev.deal_id=g.id_negocio
  LEFT JOIN inmo_mx im ON im.deal_id=g.id_negocio
  LEFT JOIN mart m ON m.nid=g.nid AND m.pais='mexico'
  LEFT JOIN pq_mx pq ON pq.nid=g.nid
  LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_state` st ON st.id=ea.cur
  WHERE hd.utm_campaign='mex-sellers-paid-experiments-web-without-leads-retargeting-national-reinteresados'
    AND g.fuente_id=3
  QUALIFY ROW_NUMBER() OVER (PARTITION BY g.nid ORDER BY CAST(g.fecha_creacion AS DATE) DESC)=1
),
-- ===== COLOMBIA =====
ea_co AS (
  SELECT negocio_id, ARRAY_AGG(estado_id ORDER BY fecha_actualizacion DESC, id DESC LIMIT 1)[OFFSET(0)] AS cur
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2` GROUP BY negocio_id
),
ever_co AS (
  SELECT negocio_id, MAX(IF(estado_id IN (20,63),1,0)) ever_calif, MAX(IF(estado_id=27,1,0)) ever_cita
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2` GROUP BY negocio_id
),
co AS (
  SELECT 'CO' AS pais,
    COALESCE(NULLIF(TRIM(g.ciudad),''),'Sin dato') AS geo,
    COALESCE(NULLIF(TRIM(g.area_metropolitana),''),'Sin dato') AS area,
    CAST(ea.cur AS STRING) AS sid, COALESCE(st.label,'Sin estado') AS slabel,
    COALESCE(ev.ever_calif,0) AS calif, COALESCE(im.ever_calif_inmo,0) AS calif_inmo,
    COALESCE(ev.ever_cita,0) AS cita,
    COALESCE(pq.gabi,0) AS gabi,
    IF(hd.hubspot_owner_id IS NOT NULL AND hd.hubspot_owner_id != '',1,0) AS owner,
    IF(m.nid IS NOT NULL,1,0) AS asig,
    IF(g.oportunidad_del_negocio='Cierre - Comprado',1,0) AS cierre,
    IF(hd.oportunidad_inmobiliaria='Contrato firmado',1,0) AS contrato,
    CAST(CAST(g.fecha_creacion AS DATE) AS STRING) AS fc
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g
  JOIN `sellers-main-prod.hubspot.deals` hd ON hd.nid=g.nid AND hd.country='Colombia'
  LEFT JOIN ea_co ea ON ea.negocio_id=g.negocio_id
  LEFT JOIN ever_co ev ON ev.negocio_id=g.negocio_id
  LEFT JOIN inmo_co im ON im.deal_id=g.negocio_id
  LEFT JOIN mart m ON m.nid=g.nid AND m.pais='colombia'
  LEFT JOIN pq_co pq ON pq.nid=g.nid
  LEFT JOIN `sellers-main-prod.co_rds_staging.habi_db_tabla_estados` st ON st.id=ea.cur
  WHERE hd.utm_campaign='col-sellers-paid-experiments-web-without-leads-retargeting-national-reinteresados'
    AND g.fuente_id IN (3, 47)   -- CO: WEB + Lead Forms (Habímetro=7 se deja morir en "sin gestión"). MX = solo 3 (ver arriba).
  QUALIFY ROW_NUMBER() OVER (PARTITION BY g.nid ORDER BY CAST(g.fecha_creacion AS DATE) DESC)=1
)
SELECT * FROM mx UNION ALL SELECT * FROM co
