WITH ult AS (
  SELECT deal_id, messages, deal, last_activity, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id, ANY_VALUE(deal) AS deal, MAX(last_activity) AS la,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
g AS (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.gabi_mx`),
f AS (
  SELECT
    CASE
      WHEN REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Recibimos tu solicitud') THEN 'B_6juntos'
      WHEN REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Has solicitado una Oferta') THEN 'A_de_a_uno'
      ELSE 'C_otra' END AS bot,
    IFNULL(REGEXP_EXTRACT(deal, r"'seller_flag': '([^']*)'"), 'sin_flag') AS seller_flag,
    EXTRACT(YEAR FROM la) AS anio,
    ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) AS t_user,
    IF(g.deal_id IS NULL, 0, 1) AS agendo
  FROM conv LEFT JOIN g ON conv.deal_id = g.deal_id
)
SELECT bot, seller_flag, COUNT(*) AS deals,
  ROUND(100*AVG(IF(t_user>0,1,0)),1) AS pct_respondio,
  ROUND(100*AVG(agendo),1)           AS pct_agendo,
  COUNTIF(agendo=1)                  AS n_agendo
FROM f WHERE bot != 'C_otra'
GROUP BY 1,2 ORDER BY 2,1
