WITH ult AS (
  SELECT deal_id, messages, AB, deal, last_activity, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id,
    ANY_VALUE(AB) AS ab, ANY_VALUE(deal) AS deal,
    MAX(last_activity) AS last_activity,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
f AS (
  SELECT
    REGEXP_EXTRACT(ab, r"'property_basic': '([^']*)'") AS brazo,
    REGEXP_EXTRACT(ab, r"'migration_4o': '([^']*)'")   AS modelo,
    REGEXP_EXTRACT(deal, r"'business_opportunity_label': '([^']*)'") AS label,
    DATE(last_activity) AS dia,
    ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) AS t_user,
    ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Gabi:'))    AS t_gabi,
    REGEXP_CONTAINS(c, r'propiedades\.com|suficientes datos comparativos|cobertura en la zona') AS rechazo_cob,
    REGEXP_CONTAINS(c, r'(?i)ya tengo toda la información|información necesaria sobre tu inmueble') AS cerro_ok,
    LENGTH(c) AS chars
  FROM conv
  WHERE REGEXP_CONTAINS(ab, r"'property_basic'")
)
SELECT
  brazo,
  COUNT(*) AS deals,
  ROUND(100*AVG(IF(t_user>0,1,0)),1)      AS pct_respondio,
  ROUND(AVG(t_user),2)                     AS turnos_user_prom,
  APPROX_QUANTILES(t_user,2)[OFFSET(1)]    AS turnos_user_med,
  ROUND(100*AVG(IF(cerro_ok,1,0)),1)       AS pct_levantamiento_ok,
  ROUND(100*AVG(IF(rechazo_cob,1,0)),1)    AS pct_rechazo_cobertura,
  ROUND(100*AVG(IF(label IN ('Cita Agendada','Visita Efectuada','Captado para inmobiliaria','Cierre - Comprado'),1,0)),1) AS pct_outcome_bueno,
  ROUND(100*AVG(IF(label='Captado para inmobiliaria',1,0)),1) AS pct_captado,
  ROUND(100*AVG(IF(label='Cita Agendada',1,0)),1)             AS pct_cita,
  ROUND(100*AVG(IF(label IS NULL,1,0)),1)                     AS pct_sin_label,
  MIN(dia) AS desde, MAX(dia) AS hasta
FROM f GROUP BY 1 ORDER BY 1
