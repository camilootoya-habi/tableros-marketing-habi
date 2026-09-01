SELECT AB, COUNT(DISTINCT deal_id) AS deals
FROM `sellers-main-prod.chatbots.mabi_mx`
WHERE AB IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC LIMIT 25
