SELECT deal_id, COUNT(*) AS filas,
       COUNT(DISTINCT last_execution_timestamp) AS ejecs,
       COUNT(DISTINCT messages) AS msgs_distintos,
       AVG(LENGTH(messages)) AS len_prom, MAX(LENGTH(messages)) AS len_max
FROM `sellers-main-prod.chatbots.mabi_mx`
GROUP BY 1 ORDER BY filas DESC LIMIT 5
