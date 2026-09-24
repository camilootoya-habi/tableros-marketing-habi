SELECT
  REGEXP_EXTRACT(deal, r"'business_opportunity_label': '([^']*)'") AS label,
  COUNT(DISTINCT deal_id) AS deals,
  COUNT(*) AS filas
FROM `sellers-main-prod.chatbots.mabi_mx`
GROUP BY 1 ORDER BY 2 DESC LIMIT 25
