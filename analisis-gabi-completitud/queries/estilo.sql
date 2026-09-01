WITH ult AS (
  SELECT deal_id, messages, AB, deal, last_activity, last_execution_timestamp
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
    CASE
      WHEN REGEXP_CONTAINS(c, r'Ya anoté|Recibimos tu solicitud') THEN 'B_guionado'
      WHEN REGEXP_CONTAINS(c, r'yo misma atenderé|Has solicitado una Oferta') THEN 'A_LLM_libre'
      ELSE 'C_otro' END AS estilo,
    IFNULL(REGEXP_EXTRACT(conv.ab, r"'migration_4o': '([^']*)'"), 'sin_flag') AS modelo,
    REGEXP_EXTRACT(deal, r"'business_opportunity_label': '([^']*)'") AS label,
    IFNULL(REGEXP_EXTRACT(deal, r"'seller_flag': '([^']*)'"), 'sin_flag') AS seller_flag,
    ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) AS t_user,
    IF(g.deal_id IS NULL, 0, 1) AS llego_agendamiento
  FROM conv LEFT JOIN g ON conv.deal_id = g.deal_id
)
SELECT estilo, COUNT(*) AS deals,
  ROUND(100*AVG(IF(t_user=0,1,0)),1)          AS pct_nunca_respondio,
  ROUND(100*AVG(llego_agendamiento),1)        AS pct_llego_a_agendar,
  ROUND(100*AVG(IF(label='Cita Agendada',1,0)),1) AS pct_cita,
  ROUND(100*AVG(IF(label='Captado para inmobiliaria',1,0)),1) AS pct_captado,
  ROUND(AVG(t_user),1) AS turnos_user
FROM f GROUP BY 1 ORDER BY 1
