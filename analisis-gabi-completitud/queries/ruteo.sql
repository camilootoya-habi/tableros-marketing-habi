WITH ult AS (
  SELECT deal_id, nid, messages, deal, last_activity, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id, ANY_VALUE(nid) AS nid, ANY_VALUE(deal) AS deal, MAX(last_activity) AS la,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
g  AS (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.gabi_mx`),
gi AS (SELECT DISTINCT nid FROM `sellers-main-prod.chatbots.gabi_inmo_mx` WHERE nid IS NOT NULL),
f AS (
  SELECT
    CASE
      WHEN REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Recibimos tu solicitud') THEN 'B_6juntos'
      WHEN REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Has solicitado una Oferta') THEN 'A_de_a_uno'
      ELSE 'C' END AS bot,
    IFNULL(REGEXP_EXTRACT(deal, r"'seller_flag': '([^']*)'"), 'sin_flag') AS sf,
    IF(g.deal_id IS NULL, 0, 1)  AS agendo,
    IF(gi.nid IS NULL, 0, 1)     AS inmo
  FROM conv
  LEFT JOIN g  ON conv.deal_id = g.deal_id
  LEFT JOIN gi ON conv.nid = gi.nid
  WHERE EXTRACT(YEAR FROM la) = 2026
)
SELECT bot, sf, COUNT(*) AS deals,
  ROUND(100*AVG(agendo),1) AS pct_gabi_agenda,
  ROUND(100*AVG(inmo),1)   AS pct_gabi_inmo,
  ROUND(100*AVG(IF(agendo=1 OR inmo=1,1,0)),1) AS pct_cualquiera
FROM f WHERE bot != 'C' AND sf IN ('ibuyer','real_estate') GROUP BY 1,2 ORDER BY 2,1
