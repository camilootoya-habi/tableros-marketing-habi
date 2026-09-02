-- Export de conversaciones de Gabi (bots A y B, jun-ago 2026) para la detección de bugs del agente.
-- 1 fila = 1 deal_id (última ejecución; mensajes agregados por HORA). ~2,4 GB por pasada.
-- El resultado tiene PII (nombres, teléfonos, direcciones): se guarda en bugs/data/ (gitignored).
-- Etapas de muerte: mismos CASE que queries/muerte_por_etapa_desenlace.sql (B) y queries/funnel_etapas_botA.sql (A).
WITH ult AS (
  SELECT deal_id, nid, messages, last_activity, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  WHERE last_activity BETWEEN DATETIME '2026-06-01' AND DATETIME '2026-08-31 23:59:59'
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id, ANY_VALUE(nid) AS nid, MAX(last_activity) AS la,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
g  AS (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.gabi_mx`),
gi AS (SELECT DISTINCT nid FROM `sellers-main-prod.chatbots.gabi_inmo_mx` WHERE nid IS NOT NULL),
f AS (
  SELECT conv.deal_id, la, c,
    CASE
      WHEN REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Recibimos tu solicitud')    THEN 'B'
      WHEN REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Has solicitado una Oferta') THEN 'A'
      ELSE 'OTRO' END AS bot,
    SUBSTR((SELECT MAX(h) FROM UNNEST(REGEXP_EXTRACT_ALL(c, r'HORA: ([0-9T:.\-]+)')) h), 1, 7) AS ult_mes_real,
    IF(g.deal_id IS NULL, 0, 1) AS agendo,
    IF(gi.nid   IS NULL, 0, 1)  AS inmo
  FROM conv
  LEFT JOIN g  ON conv.deal_id = g.deal_id
  LEFT JOIN gi ON conv.nid = gi.nid
)
SELECT deal_id, bot, DATE(la) AS last_activity, agendo, inmo,
  CASE
    WHEN bot = 'B' THEN
      CASE
        WHEN ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) = 0 THEN '1_nunca_respondio'
        WHEN NOT REGEXP_CONTAINS(c, r'(?i)\*direcci[óo]n\*') THEN '2_murio_en_tipo'
        WHEN NOT REGEXP_CONTAINS(c, r'(?i)\*antig[üu]edad\*') THEN '3_murio_en_direccion'
        WHEN NOT REGEXP_CONTAINS(IFNULL(REGEXP_EXTRACT(c, r'(?si)\*antig[üu]edad\*(.*)$'), ''), r'Usuario:') THEN '4_murio_ante_bloque'
        WHEN REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?[áa]rea construida')
             AND NOT REGEXP_CONTAINS(
               IFNULL(REGEXP_EXTRACT(c, r'(?si)^.*falta[\s\S]{0,200}?[áa]rea construida(.*)$'), 'Usuario:'),
               r'Usuario:') THEN '5_murio_en_reask_m2'
        ELSE '6_completo_o_paso' END
    ELSE
      CASE
        WHEN ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) = 0 THEN '1_nunca_respondio'
        WHEN NOT REGEXP_CONTAINS(c, r'(?mi)^Gabi:[^\n]*direcci[óo]n') THEN '2_murio_en_consentimiento'
        WHEN NOT REGEXP_CONTAINS(c, r'(?i)antig[üu]edad') THEN '3_murio_en_direccion'
        WHEN NOT REGEXP_CONTAINS(c, r'(?mi)^Gabi:[^\n]*(casa sola|departamento en condominio|edificio solo|metros cuadrados|m²)') THEN '4_murio_en_antiguedad_precio'
        WHEN NOT REGEXP_CONTAINS(c, r'(?i)ba[ñn]os completos|cu[áa]ntos ba[ñn]os') THEN '5_murio_en_tipo_m2_recamaras'
        WHEN NOT REGEXP_CONTAINS(c, r'(?i)tengo toda la informaci[óo]n|Terminamos de analizar tu solicitud') THEN '6_murio_en_banos_estac'
        ELSE '7_completo' END
  END AS etapa_muerte,
  c
FROM f
WHERE bot = 'B'
   OR (bot = 'A' AND ult_mes_real IN ('2026-06', '2026-07', '2026-08'))
