WITH ult AS (
  SELECT deal_id, messages, deal, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id, ANY_VALUE(deal) AS deal,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
g AS (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.gabi_mx`),
f AS (
  SELECT
    CASE
      WHEN REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Recibimos tu solicitud') THEN 'B_apertura_guionada'
      WHEN REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Has solicitado una Oferta') THEN 'A_apertura_LLM'
      ELSE 'C_otra_apertura' END AS apertura,
    REGEXP_CONTAINS(c, r'(?i)en un solo mensaje|todos juntos') AS llego_al_bloque,
    ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) AS t_user,
    REGEXP_EXTRACT(deal, r"'business_opportunity_label': '([^']*)'") AS label,
    IF(g.deal_id IS NULL, 0, 1) AS agendo
  FROM conv LEFT JOIN g ON conv.deal_id = g.deal_id
)
SELECT apertura, COUNT(*) AS deals,
  ROUND(100*AVG(IF(t_user>0,1,0)),1)  AS pct_respondio,
  ROUND(100*AVG(IF(llego_al_bloque,1,0)),1)   AS pct_llego_al_bloque,
  ROUND(100*AVG(agendo),1)            AS pct_llego_a_agendar,
  ROUND(100*AVG(IF(label='Captado para inmobiliaria',1,0)),1) AS pct_captado,
  ROUND(AVG(t_user),1) AS turnos_user
FROM f GROUP BY 1 ORDER BY 1
