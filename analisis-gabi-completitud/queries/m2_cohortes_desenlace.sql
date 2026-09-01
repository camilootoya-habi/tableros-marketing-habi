-- Cohortes del bloque de 6 datos (bot B, jun-ago 2026) y su desenlace de negocio.
-- DIO_TODO   = respondió el bloque y Gabi NO tuvo que re-preguntar el área.
-- PASO_M2    = le re-preguntaron el área construida y respondió.
-- MURIO_EN_M2= le re-preguntaron el área construida y no volvió a escribir.
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
  SELECT
    conv.deal_id, DATE_TRUNC(DATE(la), MONTH) AS mes,
    REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?[áa]rea construida') AS reask_m2,
    REGEXP_CONTAINS(
      IFNULL(REGEXP_EXTRACT(c, r'(?si)^.*falta[\s\S]{0,200}?[áa]rea construida(.*)$'), 'Usuario:'),
      r'Usuario:') AS respondio_tras_reask,
    REGEXP_CONTAINS(c, r'(?i)no contamos con suficientes datos comparativos|sin cobertura') AS rechazo_cobertura,
    IF(g.deal_id IS NULL, 0, 1) AS agendo,
    IF(gi.nid   IS NULL, 0, 1)  AS inmo
  FROM conv
  LEFT JOIN g  ON conv.deal_id = g.deal_id
  LEFT JOIN gi ON conv.nid = gi.nid
  WHERE REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Recibimos tu solicitud')
    AND REGEXP_CONTAINS(IFNULL(REGEXP_EXTRACT(c, r'(?si)\*antig[üu]edad\*(.*)$'), ''), r'Usuario:')  -- respondió el bloque
)
SELECT
  CASE
    WHEN NOT reask_m2 THEN 'DIO_TODO'
    WHEN respondio_tras_reask THEN 'PASO_M2'
    ELSE 'MURIO_EN_M2' END AS cohorte,
  COUNT(*) AS deals,
  COUNTIF(mes = DATE '2026-06-01') AS jun,
  COUNTIF(mes = DATE '2026-07-01') AS jul,
  COUNTIF(mes = DATE '2026-08-01') AS ago,
  ROUND(100*AVG(IF(agendo=1,1,0)),1)           AS pct_agendo,
  ROUND(100*AVG(inmo),1)                       AS pct_inmo,
  ROUND(100*AVG(IF(agendo=1 OR inmo=1,1,0)),1) AS pct_ruteado,
  ROUND(100*AVG(IF(rechazo_cobertura,1,0)),1)  AS pct_rechazo_cobertura
FROM f GROUP BY 1 ORDER BY 1
