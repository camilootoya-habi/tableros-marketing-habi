WITH ult AS (
  SELECT deal_id, messages, AB, deal, last_activity, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id, ANY_VALUE(AB) AS ab, ANY_VALUE(deal) AS deal,
    MAX(last_activity) AS last_activity,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
f AS (
  SELECT
    IFNULL(REGEXP_EXTRACT(ab, r"'property_basic': '([^']*)'"), 'SIN_FLAG') AS brazo,
    REGEXP_EXTRACT(deal, r"'business_opportunity_label': '([^']*)'") AS label,
    REGEXP_EXTRACT(deal, r"'seller_flag': '([^']*)'") AS seller_flag,
    DATE_TRUNC(DATE(last_activity), YEAR) AS anio,
    ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) AS t_user
  FROM conv
)
SELECT brazo, seller_flag, COUNT(*) AS deals,
  COUNTIF(label IN ('Cita Agendada','Visita Efectuada','Captado para inmobiliaria','Cierre - Comprado')) AS exitos,
  COUNTIF(label='Captado para inmobiliaria') AS captados,
  COUNTIF(t_user=0) AS nunca_respondio
FROM f GROUP BY 1,2 ORDER BY 1,3 DESC LIMIT 20
