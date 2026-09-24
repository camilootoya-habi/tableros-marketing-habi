-- Leads recreados (UTM reinteresados) con fecha de creación, deal_id (=id_negocio del backbone), estado actual y si calificaron (Market Maker 20/63). MX + CO.
-- Se enlaza al ledger por new_nid (backbone-leads/mapping) o por decoy_deal_id=id_negocio (decoy, que no guarda nid). El deal_id destraba las recreaciones decoy.
-- estado_id/estado_label = estado ACTUAL del backbone (id_ultimo_estado MX / last_estado_id CO) + label del catálogo → alimenta el antifunnel del tablero.
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
       IF(g.id_ultimo_estado IN (20,63), 1, 0) AS calif,
       CAST(g.id_ultimo_estado AS STRING) AS estado_id,
       COALESCE(NULLIF(TRIM(cat.label),''), CONCAT('estado_', CAST(g.id_ultimo_estado AS STRING))) AS estado_label
FROM re_mx re
JOIN `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g ON g.nid = re.nid
LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_state` cat ON cat.id = g.id_ultimo_estado
WHERE COALESCE(g.fuente_id, 0) <> 4   -- excluye Web Scraping (basura legacy del compañero, no es parte del programa)
UNION ALL
SELECT 'CO' AS pais, re.nid, CAST(g.negocio_id AS STRING) AS deal_id, re.fecha AS fecha_creacion,
       IF(g.last_estado_id IN (20,63), 1, 0) AS calif,
       CAST(g.last_estado_id AS STRING) AS estado_id,
       COALESCE(NULLIF(TRIM(cat.label),''), CONCAT('estado_', CAST(g.last_estado_id AS STRING))) AS estado_label
FROM re_co re
JOIN `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g ON g.nid = re.nid
LEFT JOIN `sellers-main-prod.co_rds_staging.habi_db_tabla_estados` cat ON cat.id = g.last_estado_id
WHERE COALESCE(g.fuente_id, 0) <> 4   -- excluye Web Scraping (simetría con MX; CO no tiene fuente 4 hoy)
