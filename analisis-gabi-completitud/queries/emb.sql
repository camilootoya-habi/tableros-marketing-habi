WITH m AS (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.mabi_mx`),
     g AS (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.gabi_mx`)
SELECT
  (SELECT COUNT(*) FROM m) AS mabi_deals,
  (SELECT COUNT(*) FROM g) AS gabi_deals,
  (SELECT COUNT(*) FROM m JOIN g USING (deal_id)) AS en_ambas,
  (SELECT COUNT(*) FROM g LEFT JOIN m USING (deal_id) WHERE m.deal_id IS NULL) AS solo_gabi
