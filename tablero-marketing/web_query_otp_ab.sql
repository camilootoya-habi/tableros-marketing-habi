-- Hoja "OTP" — A/B: con OTP vs sin OTP, CO + MX
-- Sources: {co,mx}_segment_profiles.{pages,user_interaction,select_content} + negocio
--
-- Universo: visitantes que llegaron a /formulario-inmueble/contacto. La asignación se
-- observa como ITT (intention-to-treat): `con_otp = 1` si existe `otp_request_sent` ese
-- mismo día — igual que EXP-011, porque todo el brazo tratado recibe el envío.
--
-- ⚠️ MÉTRICA PRIMARIA = Contacto → Características.
--    EXP-011 midió Contacto → Form completado, que mete adentro 2-3 pasos MÁS del
--    formulario (Contacto es el paso 2 de 4, no el último). Características es el paso
--    obligatorio inmediatamente siguiente al OTP: si el OTP te bloquea, no llegas ahí.
--    Esa es la lectura limpia de la fricción.
--
-- ⚠️ `lead` cierra el pendiente que EXP-011 dejó abierto ("cuantificar la caída de
--    volumen en el paso OTP"). El lead se crea AL PASAR el OTP (~110s después de
--    validar), así que la compuerta es medible: quien valida obtiene lead ~100%,
--    quien no, ~8%.
--
-- La fecha del `select_content` se ancla al MISMO DÍA de la visita y en hora LOCAL:
-- DATE() sobre un TIMESTAMP evalúa en UTC y corre la ventana un día para el tráfico
-- nocturno (bug medido 2026-09-02, costaba 38% de los leads).

WITH contacto AS (
  SELECT 'MX' AS pais, anonymous_id, DATE(timestamp, 'America/Mexico_City') AS d
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Mexico_City') >= '2026-05-01'
    AND DATE(timestamp, 'America/Mexico_City') < CURRENT_DATE()
    AND context_page_path = '/formulario-inmueble/contacto' AND context_page_url LIKE '%habi.mx%'
    AND anonymous_id IS NOT NULL
  GROUP BY 1, 2, 3
  UNION ALL
  SELECT 'CO', anonymous_id, DATE(timestamp, 'America/Bogota')
  FROM `sellers-main-prod.co_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Bogota') >= '2026-05-01'
    AND DATE(timestamp, 'America/Bogota') < CURRENT_DATE()
    AND context_page_path = '/formulario-inmueble/contacto' AND context_page_url LIKE '%habi.co%'
    AND anonymous_id IS NOT NULL
  GROUP BY 1, 2, 3
),

-- pasos posteriores (mismo visitante, cualquier momento)
avanza AS (
  SELECT 'MX' AS pais, anonymous_id,
    MAX(IF(context_page_path = '/formulario-inmueble/caracteristicas', 1, 0)) AS caracteristicas,
    MAX(IF(context_page_path = '/formulario-inmueble/felicitaciones', 1, 0))  AS felicitaciones
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Mexico_City') >= '2026-05-01' AND context_page_url LIKE '%habi.mx%'
  GROUP BY 1, 2
  UNION ALL
  SELECT 'CO', anonymous_id,
    MAX(IF(context_page_path = '/formulario-inmueble/caracteristicas', 1, 0)),
    MAX(IF(context_page_path = '/formulario-inmueble/felicitaciones', 1, 0))
  FROM `sellers-main-prod.co_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Bogota') >= '2026-05-01' AND context_page_url LIKE '%habi.co%'
  GROUP BY 1, 2
),

otp AS (
  SELECT 'MX' AS pais, anonymous_id, DATE(sent_at, 'America/Mexico_City') AS d,
         MAX(IF(event_name = 'otp_request_sent', 1, 0))       AS request,
         MAX(IF(event_name = 'otp_validation_success', 1, 0)) AS valida
  FROM `sellers-main-prod.mx_segment_profiles.user_interaction`
  WHERE DATE(sent_at, 'America/Mexico_City') >= '2026-05-01' AND LOWER(event_name) LIKE '%otp%'
  GROUP BY 1, 2, 3
  UNION ALL
  SELECT 'CO', anonymous_id, DATE(sent_at, 'America/Bogota'),
         MAX(IF(event_name = 'otp_request_sent', 1, 0)),
         MAX(IF(event_name = 'otp_validation_success', 1, 0))
  FROM `sellers-main-prod.co_segment_profiles.user_interaction`
  WHERE DATE(sent_at, 'America/Bogota') >= '2026-05-01' AND LOWER(event_name) LIKE '%otp%'
  GROUP BY 1, 2, 3
),

sc AS (
  SELECT 'MX' AS pais, anonymous_id, backbone_uuid, DATE(timestamp, 'America/Mexico_City') AS d
  FROM `sellers-main-prod.mx_segment_profiles.select_content`
  WHERE DATE(timestamp, 'America/Mexico_City') >= '2026-05-01' AND backbone_uuid IS NOT NULL
  UNION ALL
  SELECT 'CO', anonymous_id, backbone_uuid, DATE(timestamp, 'America/Bogota')
  FROM `sellers-main-prod.co_segment_profiles.select_content`
  WHERE DATE(timestamp, 'America/Bogota') >= '2026-05-01' AND backbone_uuid IS NOT NULL
),
br AS (
  SELECT uuid, deal_uuid FROM `sellers-main-prod.top_funnel.web_global_api_business`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY uuid ORDER BY deal_uuid) = 1
),
deals AS (
  SELECT 'MX' AS pais, uuid, nid, DATE(date_create) AS d_deal, last_state_id AS estado
  FROM `sellers-main-prod.mx_rds_staging.habi_db_property_deal` WHERE nid IS NOT NULL
  UNION ALL
  SELECT 'CO', uuid, nid, DATE(fecha_creacion), last_estado_id
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` WHERE nid IS NOT NULL
),
lead AS (
  SELECT DISTINCT sc.pais, sc.anonymous_id, sc.d,
         dl.nid, IF(dl.estado IN (20, 63), 1, 0) AS calificado
  FROM sc
  JOIN br ON br.uuid = sc.backbone_uuid
  JOIN deals dl ON dl.uuid = br.deal_uuid AND dl.pais = sc.pais AND dl.d_deal = sc.d
),

base AS (
  SELECT c.pais, c.d,
    IFNULL(o.request, 0) AS con_otp,
    IFNULL(o.valida, 0)  AS valida_otp,
    IFNULL(a.caracteristicas, 0) AS caracteristicas,
    IFNULL(a.felicitaciones, 0)  AS felicitaciones,
    IF(l.nid IS NOT NULL, 1, 0)  AS lead,
    IFNULL(l.calificado, 0)      AS calificado
  FROM contacto c
  LEFT JOIN otp o    ON o.pais = c.pais AND o.anonymous_id = c.anonymous_id AND o.d = c.d
  LEFT JOIN avanza a ON a.pais = c.pais AND a.anonymous_id = c.anonymous_id
  LEFT JOIN lead l   ON l.pais = c.pais AND l.anonymous_id = c.anonymous_id AND l.d = c.d
)

SELECT pais, CAST(d AS STRING) AS dia,
  CASE
    WHEN d < '2026-05-22' THEN 'sin OTP'
    WHEN d <= '2026-07-13' THEN 'A/B v1'
    WHEN d = '2026-08-20' THEN 'falla total'
    WHEN pais = 'MX' AND d BETWEEN '2026-08-03' AND '2026-08-14' THEN 'degradado SNS'
    WHEN d <= '2026-08-19' THEN 'rollout 100%'
    WHEN d <= '2026-09-01' THEN 'apagado'
    ELSE 'A/B v2 (50%)'
  END AS regimen,
  con_otp,
  COUNT(*)                    AS n_contacto,
  SUM(valida_otp)             AS valida_otp,
  SUM(caracteristicas)        AS n_caracteristicas,
  SUM(felicitaciones)         AS n_felicitaciones,
  SUM(lead)                   AS n_lead,
  SUM(calificado)             AS n_calificado
FROM base
GROUP BY 1, 2, 3, 4
ORDER BY pais, dia, con_otp
