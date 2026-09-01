-- Completitud por etapa del funnel de Gabi (bot B guionado "Recibimos tu solicitud")
-- Ventana: last_activity 2026-06-01 .. 2026-08-31. 1 conversación = 1 deal_id (última ejecución).
-- OJO: los textos de Gabi los redacta un LLM y varían; los marcadores son genéricos y case-insensitive.
WITH ult AS (
  SELECT deal_id, nid, messages, deal, last_activity, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  WHERE last_activity BETWEEN DATETIME '2026-06-01' AND DATETIME '2026-08-31 23:59:59'
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id, ANY_VALUE(nid) AS nid, ANY_VALUE(deal) AS deal,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
g  AS (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.gabi_mx`),
gi AS (SELECT DISTINCT nid FROM `sellers-main-prod.chatbots.gabi_inmo_mx` WHERE nid IS NOT NULL),
f AS (
  SELECT
    conv.deal_id,
    REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Recibimos tu solicitud') AS es_bot_b,
    ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) > 0                                    AS e1_respondio,
    -- Gabi menciona *dirección* => el usuario ya contestó tipo de inmueble
    REGEXP_CONTAINS(c, r'(?i)\*direcci[óo]n\*')                                                  AS e2_llego_a_direccion,
    -- Gabi pide el bloque de 6 datos (antigüedad solo aparece ahí)
    REGEXP_CONTAINS(c, r'(?i)\*antig[üu]edad\*')                                                 AS e3_llego_al_bloque,
    -- turno de usuario DESPUÉS de pedir el bloque
    REGEXP_CONTAINS(IFNULL(REGEXP_EXTRACT(c, r'(?si)\*antig[üu]edad\*(.*)$'), ''), r'Usuario:')  AS e4_respondio_bloque,
    -- re-pregunta de área construida ("Solo me falta ... área construida" y variantes)
    REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?[áa]rea construida')                             AS reask_m2,
    -- ¿la re-pregunta era SOLO por m² o por varios campos a la vez?
    REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?[áa]rea construida[\s\S]{0,120}?(rec[áa]maras|ba[ñn]os|cajones|valor|precio)') AS reask_multi,
    -- texto después de la ÚLTIMA re-pregunta de m² (greedy ^.* empuja a la última)
    REGEXP_CONTAINS(
      IFNULL(REGEXP_EXTRACT(c, r'(?si)^.*falta[\s\S]{0,200}?[áa]rea construida(.*)$'), 'Usuario:'),
      r'Usuario:')                                                                               AS respondio_tras_reask_m2,
    -- desenlaces observables en la conversación / tablas de ruteo
    REGEXP_CONTAINS(c, r'(?i)no contamos con suficientes datos comparativos|sin cobertura')      AS rechazo_cobertura,
    IF(g.deal_id IS NULL, 0, 1)  AS agendo,
    IF(gi.nid   IS NULL, 0, 1)   AS inmo
  FROM conv
  LEFT JOIN g  ON conv.deal_id = g.deal_id
  LEFT JOIN gi ON conv.nid = gi.nid
)
SELECT
  COUNT(*)                                                        AS deals_bot_b,
  COUNTIF(e1_respondio)                                           AS e1_respondio,
  COUNTIF(e2_llego_a_direccion)                                   AS e2_llego_a_direccion,
  COUNTIF(e3_llego_al_bloque)                                     AS e3_llego_al_bloque,
  COUNTIF(e4_respondio_bloque)                                    AS e4_respondio_bloque,
  COUNTIF(reask_m2)                                               AS reask_m2,
  COUNTIF(reask_m2 AND NOT reask_multi)                           AS reask_m2_solo,
  COUNTIF(reask_m2 AND NOT respondio_tras_reask_m2)               AS murio_en_m2,
  COUNTIF(reask_m2 AND respondio_tras_reask_m2)                   AS paso_m2,
  COUNTIF(reask_m2 AND NOT reask_multi AND NOT respondio_tras_reask_m2) AS murio_en_m2_solo,
  COUNTIF(rechazo_cobertura)                                      AS rechazo_cobertura,
  COUNTIF(agendo = 1)                                             AS agendo,
  COUNTIF(inmo = 1)                                               AS inmo
FROM f
WHERE es_bot_b
