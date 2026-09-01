-- ¿En qué etapa muere cada conversación del bot B (jun-ago 2026) y qué pasa después con el deal?
-- "ruteado" = el deal aparece luego en gabi_mx (agenda) o gabi_inmo_mx (inmobiliaria).
WITH ult AS (
  SELECT deal_id, nid, messages, last_activity, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  WHERE last_activity BETWEEN DATETIME '2026-06-01' AND DATETIME '2026-08-31 23:59:59'
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id, ANY_VALUE(nid) AS nid,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
g  AS (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.gabi_mx`),
gi AS (SELECT DISTINCT nid FROM `sellers-main-prod.chatbots.gabi_inmo_mx` WHERE nid IS NOT NULL),
f AS (
  SELECT conv.deal_id,
    CASE
      WHEN ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) = 0 THEN '1_nunca_respondio'
      WHEN NOT REGEXP_CONTAINS(c, r'(?i)\*direcci[óo]n\*') THEN '2_murio_en_tipo'
      WHEN NOT REGEXP_CONTAINS(c, r'(?i)\*antig[üu]edad\*') THEN '3_murio_en_direccion'
      WHEN NOT REGEXP_CONTAINS(IFNULL(REGEXP_EXTRACT(c, r'(?si)\*antig[üu]edad\*(.*)$'), ''), r'Usuario:') THEN '4_murio_ante_bloque'
      WHEN REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?[áa]rea construida')
           AND NOT REGEXP_CONTAINS(
             IFNULL(REGEXP_EXTRACT(c, r'(?si)^.*falta[\s\S]{0,200}?[áa]rea construida(.*)$'), 'Usuario:'),
             r'Usuario:') THEN '5_murio_en_reask_m2'
      ELSE '6_completo_o_paso' END AS etapa_muerte,
    IF(g.deal_id IS NULL, 0, 1) AS agendo,
    IF(gi.nid   IS NULL, 0, 1)  AS inmo
  FROM conv
  LEFT JOIN g  ON conv.deal_id = g.deal_id
  LEFT JOIN gi ON conv.nid = gi.nid
  WHERE REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Recibimos tu solicitud')
)
SELECT etapa_muerte, COUNT(*) deals,
  ROUND(100*COUNT(*)/SUM(COUNT(*)) OVER (), 1)     AS pct_del_total,
  ROUND(100*AVG(agendo),1)                          AS pct_agenda,
  ROUND(100*AVG(inmo),1)                            AS pct_inmo,
  ROUND(100*AVG(IF(agendo=1 OR inmo=1,1,0)),1)      AS pct_ruteado
FROM f GROUP BY 1 ORDER BY 1
