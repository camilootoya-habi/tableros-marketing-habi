SELECT 'mabi_mx' AS t, COUNT(DISTINCT deal_id) AS deals, MIN(DATE(last_activity)) AS desde, MAX(DATE(last_activity)) AS hasta
FROM `sellers-main-prod.chatbots.mabi_mx`
UNION ALL
SELECT 'gabi_mx', COUNT(DISTINCT deal_id), MIN(DATE(last_activity)), MAX(DATE(last_activity))
FROM `sellers-main-prod.chatbots.gabi_mx`
UNION ALL
SELECT 'gabi_inmo_mx', COUNT(DISTINCT deal_id), MIN(DATE(last_activity)), MAX(DATE(last_activity))
FROM `sellers-main-prod.chatbots.gabi_inmo_mx`
UNION ALL
SELECT 'gabi_onboarding_mx', COUNT(DISTINCT deal_id), MIN(DATE(last_activity)), MAX(DATE(last_activity))
FROM `sellers-main-prod.chatbots.gabi_onboarding_mx`
UNION ALL
SELECT 'AMBAS mabi+gabi', COUNT(DISTINCT a.deal_id), NULL, NULL
FROM (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.mabi_mx`) a
JOIN (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.gabi_mx`) b USING (deal_id)
