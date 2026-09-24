WITH ult AS (
  SELECT deal_id, AB, DATE(last_activity) AS dia,
         ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY last_execution_timestamp DESC) AS rn
  FROM `sellers-main-prod.chatbots.mabi_mx`
)
SELECT AB, COUNT(*) AS deals, MIN(dia) AS desde, MAX(dia) AS hasta
FROM ult WHERE rn = 1
GROUP BY 1 ORDER BY 2 DESC LIMIT 15
