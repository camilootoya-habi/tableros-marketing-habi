SELECT last_execution_timestamp, COUNT(*) AS filas, SUM(LENGTH(messages)) AS chars,
       COUNT(DISTINCT SUBSTR(messages,1,60)) AS inicios
FROM `sellers-main-prod.chatbots.mabi_mx`
WHERE deal_id = 1591451
GROUP BY 1 ORDER BY 1 DESC LIMIT 8
