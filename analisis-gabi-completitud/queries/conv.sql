WITH win AS (
  SELECT deal_id, messages, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  WHERE last_activity BETWEEN DATETIME '2026-06-01' AND DATETIME '2026-08-15'
),
mx AS (SELECT deal_id, MAX(last_execution_timestamp) AS mt FROM win GROUP BY 1),
ult AS (
  SELECT w.deal_id, w.messages
  FROM win w JOIN mx ON w.deal_id = mx.deal_id AND w.last_execution_timestamp = mx.mt
),
conv AS (
  SELECT deal_id,
         STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
etiq AS (
  SELECT deal_id, c, LENGTH(c) AS n,
         SUBSTR(c, GREATEST(LENGTH(c) - 500, 1)) AS cola
  FROM conv
)
SELECT 'COMPLETA' AS caso, deal_id, n, c FROM etiq
WHERE REGEXP_CONTAINS(c, r'estacionamiento') AND n BETWEEN 3500 AND 6500
ORDER BY n LIMIT 2
