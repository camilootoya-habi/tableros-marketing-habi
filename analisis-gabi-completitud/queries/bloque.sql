WITH ult AS (
  SELECT deal_id, messages, AB, deal, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id, ANY_VALUE(AB) AS ab, ANY_VALUE(deal) AS deal,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
g AS (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.gabi_mx`),
f AS (
  SELECT
    IFNULL(REGEXP_EXTRACT(ab, r"'property_basic': '([^']*)'"), 'sin_flag') AS brazo,
    -- pidio los datos en bloque
    REGEXP_CONTAINS(c, r'(?i)en un solo mensaje|todos juntos|todo en un solo mensaje') AS pide_bloque,
    ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) AS t_user,
    ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Gabi:')) AS t_gabi,
    REGEXP_EXTRACT(deal, r"'business_opportunity_label': '([^']*)'") AS label,
    IF(g.deal_id IS NULL, 0, 1) AS agendo
  FROM conv LEFT JOIN g ON conv.deal_id = g.deal_id
)
SELECT brazo, pide_bloque, COUNT(*) AS deals,
  ROUND(100*AVG(IF(t_user=0,1,0)),1)   AS pct_nunca_respondio,
  ROUND(100*AVG(agendo),1)             AS pct_llego_a_agendar,
  ROUND(100*AVG(IF(label='Captado para inmobiliaria',1,0)),1) AS pct_captado,
  ROUND(AVG(t_user),1) AS turnos_user, ROUND(AVG(t_gabi),1) AS turnos_gabi
FROM f GROUP BY 1,2 ORDER BY 1,2
