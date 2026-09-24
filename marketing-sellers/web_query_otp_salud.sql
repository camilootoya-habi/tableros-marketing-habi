-- Hoja "OTP" — Salud diaria del OTP, CO + MX
-- Source: {co,mx}_segment_profiles.user_interaction
--
-- Una fila por (país, día) con el embudo del propio OTP y el desglose de POR QUÉ se cae
-- la gente. Se cuenta por VISITANTE (anonymous_id), no por evento: un reenvío no debe
-- inflar el denominador.
--
-- Régimen: el OTP ha pasado por seis estados y mezclarlos invalida cualquier lectura.
--   · < 2026-05-22            sin OTP
--   · 2026-05-22 → 07-13      A/B v1 (EXP-011, share aleatorio)
--   · 2026-07-14 → 08-19      rollout 100%
--   · 2026-08-03 → 08-14      ⚠️ DEGRADADO en MX (budget AWS SNS agotándose)
--   · 2026-08-20              ⚠️ falla total (se envían OTP pero nadie valida)
--   · 2026-08-21 → 09-01      apagado (sin budget de SNS)
--   · >= 2026-09-02           A/B v2 al 50% (re-encendido deliberado para medir impacto)
-- Los días marcados ⚠️ deben EXCLUIRSE de cualquier comparación: son falla de
-- infraestructura, no fricción del OTP.

WITH ev AS (
  SELECT 'MX' AS pais, anonymous_id, event_name, DATE(sent_at, 'America/Mexico_City') AS d
  FROM `sellers-main-prod.mx_segment_profiles.user_interaction`
  WHERE DATE(sent_at, 'America/Mexico_City') >= '2026-05-01'
    AND DATE(sent_at, 'America/Mexico_City') < CURRENT_DATE()
    AND LOWER(event_name) LIKE '%otp%'
  UNION ALL
  SELECT 'CO', anonymous_id, event_name, DATE(sent_at, 'America/Bogota')
  FROM `sellers-main-prod.co_segment_profiles.user_interaction`
  WHERE DATE(sent_at, 'America/Bogota') >= '2026-05-01'
    AND DATE(sent_at, 'America/Bogota') < CURRENT_DATE()
    AND LOWER(event_name) LIKE '%otp%'
),

por_visitante AS (
  SELECT pais, d, anonymous_id,
    MAX(IF(event_name = 'otp_modal_shown', 1, 0))                 AS modal,
    MAX(IF(event_name = 'otp_request_sent', 1, 0))                AS request,
    MAX(IF(event_name = 'otp_validation_success', 1, 0))          AS ok,
    MAX(IF(event_name = 'otp_validation_error', 1, 0))            AS error,
    MAX(IF(event_name = 'otp_validation_attempts_exhausted', 1, 0)) AS agotado,
    MAX(IF(event_name = 'otp_resend_requested', 1, 0))            AS reenvio,
    MAX(IF(event_name = 'otp_resend_limit_reached', 1, 0))        AS limite_reenvio,
    MAX(IF(event_name = 'otp_request_failed', 1, 0))              AS envio_fallido
  FROM ev GROUP BY 1, 2, 3
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
  COUNTIF(request = 1)                                   AS requests,
  COUNTIF(request = 1 AND ok = 1)                        AS validan,
  COUNTIF(request = 1 AND ok = 0 AND error = 0)          AS abandona_sin_intentar,
  COUNTIF(request = 1 AND ok = 0 AND error = 1)          AS intenta_y_falla,
  COUNTIF(agotado = 1)                                   AS intentos_agotados,
  COUNTIF(reenvio = 1)                                   AS pide_reenvio,
  COUNTIF(limite_reenvio = 1)                            AS tope_reenvios,
  COUNTIF(envio_fallido = 1)                             AS envio_fallido
FROM por_visitante
GROUP BY 1, 2, 3
ORDER BY pais, dia
