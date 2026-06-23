-- Funnel reinteresados (WEB) MX+CO — FUENTE: hubspot.deals (replica ~7 min de lag, refresh cada 10 min).
-- 1 fila por nid. Calificados y antifunnel son particiones complementarias del MISMO campo `estado`
-- (backbone state): calif MM = estado IN ('No gestionado','Sin pricing incial') (=20,63); resto = antifunnel.
-- Columnas: pais · geo · area · sid · slabel(estado) · calif(MM 20/63) · calif_inmo(estado_del_negocio_inmo)
--   · cita(fecha_de_visita) · owner(hubspot_owner_id) · asig(WBR mart oficial) · cierre · contrato · fc.
-- WBR mart se trae de su tabla (número oficial de asignados, no cambia por corrida). GABI eliminado.
WITH mart AS (
  SELECT DISTINCT nid, pais FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
),
base AS (
  SELECT
    CASE d.country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' END AS pais,
    CASE WHEN d.country='México'
         THEN COALESCE(NULLIF(TRIM(d.estado_de_la_republica_mexico),''), NULLIF(TRIM(d.ciudad_mx),''), 'Sin dato')
         ELSE COALESCE(NULLIF(TRIM(d.ciudad),''),'Sin dato') END AS geo,
    COALESCE(NULLIF(TRIM(d.area_metropolitana),''),'Sin dato') AS area,
    CASE d.estado WHEN 'No gestionado' THEN '20' WHEN 'Sin pricing incial' THEN '63' ELSE '' END AS sid,
    COALESCE(NULLIF(TRIM(d.estado),''),'Sin estado') AS slabel,
    IF(d.estado IN ('No gestionado','Sin pricing incial'),1,0) AS calif,
    IF(d.estado_del_negocio_inmo='No gestionado',1,0) AS calif_inmo,
    IF(d.fecha_de_visita IS NOT NULL,1,0) AS cita,
    IF(d.hubspot_owner_id IS NOT NULL AND d.hubspot_owner_id!='',1,0) AS owner,
    IF(m.nid IS NOT NULL,1,0) AS asig,
    IF(d.oportunidad_del_negocio='Cierre - Comprado',1,0) AS cierre,
    IF(d.oportunidad_inmobiliaria='Contrato firmado',1,0) AS contrato,
    COALESCE(NULLIF(TRIM(p.label),''),'Sin pipeline') AS pipeline,
    COALESCE(NULLIF(TRIM(s.label),''),'Sin etapa') AS etapa,
    CAST(COALESCE(s.display_order,999) AS INT64) AS eorden,
    CAST(CAST(d.createdate AS DATE) AS STRING) AS fc,
    d.nid,
    ROW_NUMBER() OVER (PARTITION BY d.nid ORDER BY d.createdate DESC) AS rn
  FROM `sellers-main-prod.hubspot.deals` d
  LEFT JOIN mart m
    ON m.nid = d.nid
   AND m.pais = CASE d.country WHEN 'México' THEN 'mexico' WHEN 'Colombia' THEN 'colombia' END
  LEFT JOIN `sellers-main-prod.hubspot.deal_pipelines_stages` s ON s.id = d.dealstage
  LEFT JOIN `sellers-main-prod.hubspot.deal_pipelines` p ON p.id = s.pipeline_id
  WHERE d.utm_campaign LIKE '%reinteresados%'
    AND (
      (d.country='México'   AND d.fuente='WEB') OR
      (d.country='Colombia' AND d.fuente IN ('WEB','Leadforms'))
    )
)
SELECT pais, geo, area, sid, slabel, calif, calif_inmo, cita, owner, asig, cierre, contrato, pipeline, etapa, eorden, fc
FROM base WHERE rn=1
