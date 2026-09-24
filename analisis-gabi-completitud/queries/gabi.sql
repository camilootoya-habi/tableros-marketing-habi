SELECT deal_id, SUBSTR(messages, 1, 900) AS ini
FROM `sellers-main-prod.chatbots.gabi_mx`
WHERE last_activity BETWEEN DATETIME '2026-07-01' AND DATETIME '2026-08-15'
  AND LENGTH(messages) BETWEEN 600 AND 2500
LIMIT 3
