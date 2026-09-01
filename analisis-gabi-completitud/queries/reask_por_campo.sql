-- ¿Qué campo re-pregunta Gabi tras el bloque de 6 datos? (bot B, jun-ago 2026)
-- Cuenta deals cuya conversación tiene una re-pregunta "falta ... <campo>" (ventana de 200 chars).
WITH ult AS (
  SELECT deal_id, messages, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  WHERE last_activity BETWEEN DATETIME '2026-06-01' AND DATETIME '2026-08-31 23:59:59'
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
b AS (
  SELECT deal_id, c FROM conv
  WHERE REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Recibimos tu solicitud')
    AND REGEXP_CONTAINS(IFNULL(REGEXP_EXTRACT(c, r'(?si)\*antig[üu]edad\*(.*)$'), ''), r'Usuario:')  -- respondió el bloque
)
SELECT campo, deals, ROUND(100*deals / (SELECT COUNT(*) FROM b), 1) AS pct_de_los_que_respondieron_bloque
FROM (
  SELECT '1_area_construida' AS campo, COUNTIF(REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?[áa]rea construida')) AS deals FROM b
  UNION ALL SELECT '2_valor_precio', COUNTIF(REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?(valor|precio)')) FROM b
  UNION ALL SELECT '3_antiguedad',   COUNTIF(REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?antig[üu]edad')) FROM b
  UNION ALL SELECT '4_recamaras',    COUNTIF(REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?rec[áa]maras')) FROM b
  UNION ALL SELECT '5_banos',        COUNTIF(REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?ba[ñn]os')) FROM b
  UNION ALL SELECT '6_cajones',      COUNTIF(REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?(cajones|estacionamiento)')) FROM b
  UNION ALL SELECT '0_cualquiera',   COUNTIF(REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?(área construida|area construida|valor|precio|antig[üu]edad|rec[áa]maras|ba[ñn]os|cajones|estacionamiento)')) FROM b
)
ORDER BY campo
