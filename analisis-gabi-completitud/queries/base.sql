WITH ult AS (
  SELECT deal_id, messages, AB, deal, last_activity, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id,
    ANY_VALUE(AB) AS ab, ANY_VALUE(deal) AS deal,
    MAX(last_activity) AS last_activity,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
)
SELECT
  REGEXP_EXTRACT(ab, r"'property_basic': '([^']*)'") AS pb,
  CASE
    WHEN REGEXP_CONTAINS(c, r'Ya anoté|Recibimos tu solicitud') THEN 'estructurado'
    WHEN REGEXP_CONTAINS(c, r'yo misma atenderé|Has solicitado una Oferta') THEN 'conversacional'
    ELSE 'otro' END AS estilo,
  COUNT(*) AS deals,
  MIN(DATE(last_activity)) AS desde,
  MAX(DATE(last_activity)) AS hasta
FROM conv
GROUP BY 1,2 ORDER BY 3 DESC LIMIT 30
