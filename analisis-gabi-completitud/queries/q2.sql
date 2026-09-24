SELECT
  COUNT(DISTINCT last_execution_timestamp) AS ejecuciones,
  MIN(last_execution_timestamp) AS primera,
  MAX(last_execution_timestamp) AS ultima
FROM `sellers-main-prod.chatbots.mabi_mx`
