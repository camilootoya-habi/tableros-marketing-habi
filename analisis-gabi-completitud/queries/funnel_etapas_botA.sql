-- Completitud por etapa del funnel de Gabi — BOT A ("de a uno", LLM libre,
-- apertura "¡Has solicitado una Oferta de Compra...!", excluyente con el bot B
-- porque se clasifica por la PRIMERA línea de Gabi y la apertura B es "Recibimos tu solicitud").
-- Ventana: last_activity 2026-06-01 .. 2026-08-31. 1 conversación = 1 deal_id (última ejecución).
-- Progresión real del bot A (leída en conversaciones; ver conv_completa.clean.json):
--   consentimiento ACEPTO → dirección (calle+número+CP) → antigüedad+precio → tipo de inmueble
--   y m²/recámaras (el LLM las interlava o funde: 95 convs tienen m² sin pregunta de tipo y 72 al
--   revés, así que van como UNA etapa) → baños+estacionamiento → "tengo toda la información".
-- Como pregunta DE A UNO, que Gabi formule una pregunta implica que lo anterior fue respondido.
-- Por diseño NO existen en A ni el "bloque de 6" ni la "re-pregunta de m² en mensaje aparte" del bot B.
-- ⚠ COHORTE POR FECHA REAL DE MENSAJES: en el bot A, `last_activity` se mueve sin mensajes nuevos
-- (61% de los deals A con last_activity jun-ago tienen su ÚLTIMO mensaje en 2024-2025). Se exige
-- además que el último HORA de la conversación caiga en la ventana. En el bot B esto casi no pasa
-- (97% ya caía en ventana), así que la comparación queda válida.
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
  SELECT
    conv.deal_id,
    ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) > 0                          AS a1_respondio,
    -- Gabi pide la dirección (solo la pide tras el ACEPTO del consentimiento)
    REGEXP_CONTAINS(c, r'(?mi)^Gabi:[^\n]*direcci[óo]n')                               AS a2_llego_direccion,
    -- Gabi pregunta antigüedad+precio (implica dirección entregada)
    REGEXP_CONTAINS(c, r'(?i)antig[üu]edad')                                           AS a3_llego_antiguedad,
    -- Gabi pregunta tipo de inmueble y/o m²/recámaras (etapa fundida, ver cabecera)
    REGEXP_CONTAINS(c, r'(?mi)^Gabi:[^\n]*(casa sola|departamento en condominio|edificio solo|metros cuadrados|m²)') AS a4_llego_tipo_m2,
    -- Gabi pregunta baños/estacionamiento
    REGEXP_CONTAINS(c, r'(?i)ba[ñn]os completos|cu[áa]ntos ba[ñn]os')                  AS a5_llego_banos,
    -- cierre del levantamiento de datos (marcador DÉBIL: el LLM varía el cierre)
    REGEXP_CONTAINS(c, r'(?i)tengo toda la informaci[óo]n|Terminamos de analizar tu solicitud') AS a6_completo,
    IF(g.deal_id IS NULL, 0, 1) AS agendo,
    IF(gi.nid   IS NULL, 0, 1)  AS inmo
  FROM conv
  LEFT JOIN g  ON conv.deal_id = g.deal_id
  LEFT JOIN gi ON conv.nid = gi.nid
  WHERE REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Has solicitado una Oferta')
    -- último mensaje de la conversación realmente dentro de la ventana (ver cabecera)
    AND SUBSTR((SELECT MAX(h) FROM UNNEST(REGEXP_EXTRACT_ALL(c, r'HORA: ([0-9T:.\-]+)')) h), 1, 7)
        IN ('2026-06', '2026-07', '2026-08')
)
-- (1) funnel acumulado
SELECT 'funnel_acumulado' AS bloque, NULL AS etapa_muerte,
  COUNT(*) AS deals,
  COUNTIF(a1_respondio) AS a1_respondio,
  COUNTIF(a2_llego_direccion) AS a2_llego_direccion,
  COUNTIF(a3_llego_antiguedad) AS a3_llego_antiguedad,
  COUNTIF(a4_llego_tipo_m2) AS a4_llego_tipo_m2,
  COUNTIF(a5_llego_banos) AS a5_llego_banos,
  COUNTIF(a6_completo) AS a6_completo,
  NULL AS pct_ruteado
FROM f
UNION ALL
-- (2) etapa de muerte (excluyente) × ruteo posterior a agenda/inmobiliaria
SELECT 'muerte_por_etapa', etapa_muerte, COUNT(*), NULL,NULL,NULL,NULL,NULL,NULL,
  ROUND(100*AVG(IF(agendo=1 OR inmo=1,1,0)),1)
FROM (
  SELECT *,
    CASE
      WHEN NOT a1_respondio THEN '1_nunca_respondio'
      WHEN NOT a2_llego_direccion THEN '2_murio_en_consentimiento'
      WHEN NOT a3_llego_antiguedad THEN '3_murio_en_direccion'
      WHEN NOT a4_llego_tipo_m2 THEN '4_murio_en_antiguedad_precio'
      WHEN NOT a5_llego_banos THEN '5_murio_en_tipo_m2_recamaras'
      WHEN NOT a6_completo THEN '6_murio_en_banos_estac'
      ELSE '7_completo' END AS etapa_muerte
  FROM f
) GROUP BY 2
ORDER BY bloque, etapa_muerte
