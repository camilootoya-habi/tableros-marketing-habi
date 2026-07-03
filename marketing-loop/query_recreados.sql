-- Leads recreados (UTM reinteresados) con fecha de creación, deal_id (=id_negocio del backbone) y si calificaron (Market Maker 20/63). MX + CO.
-- Se enlaza al ledger por new_nid (backbone-leads/mapping) o por decoy_deal_id=id_negocio (decoy, que no guarda nid). El deal_id destraba las recreaciones decoy.
WITH re_mx AS (
  SELECT nid, CAST(CAST(createdate AS DATE) AS STRING) AS fecha
  FROM `sellers-main-prod.hubspot.deals`
  WHERE utm_campaign LIKE '%reinteresados%' AND country='México'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
),
re_co AS (
  SELECT nid, CAST(CAST(createdate AS DATE) AS STRING) AS fecha
  FROM `sellers-main-prod.hubspot.deals`
  WHERE utm_campaign LIKE '%reinteresados%' AND country='Colombia'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
)
SELECT 'MX' AS pais, re.nid, CAST(g.id_negocio AS STRING) AS deal_id, re.fecha AS fecha_creacion,
       IF(g.id_ultimo_estado IN (20,63), 1, 0) AS calif
FROM re_mx re JOIN `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g ON g.nid = re.nid
UNION ALL
SELECT 'CO' AS pais, re.nid, CAST(g.negocio_id AS STRING) AS deal_id, re.fecha AS fecha_creacion,
       IF(g.last_estado_id IN (20,63), 1, 0) AS calif
FROM re_co re JOIN `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g ON g.nid = re.nid
