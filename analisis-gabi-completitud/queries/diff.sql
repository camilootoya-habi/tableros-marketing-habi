WITH ult AS (
  SELECT deal_id, messages, AB, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id, ANY_VALUE(AB) AS ab,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
f AS (
  SELECT REGEXP_EXTRACT(ab, r"'property_basic': '([^']*)'") AS brazo, c
  FROM conv WHERE REGEXP_CONTAINS(ab, r"'property_basic'")
),
frases AS (
  SELECT brazo, LOWER(REGEXP_REPLACE(linea, r'[0-9]+', '#')) AS frase
  FROM f, UNNEST(REGEXP_EXTRACT_ALL(c, r'(?m)^Gabi: ([^\n]{25,110})')) AS linea
)
SELECT frase,
  COUNTIF(brazo='1.0.6') AS n_106,
  COUNTIF(brazo='1.0.7') AS n_107
FROM frases
GROUP BY 1
HAVING n_106 + n_107 >= 40
   AND (LEAST(n_106,n_107) = 0 OR GREATEST(n_106,n_107)/GREATEST(LEAST(n_106,n_107),1) >= 3)
ORDER BY n_106 + n_107 DESC
LIMIT 25
