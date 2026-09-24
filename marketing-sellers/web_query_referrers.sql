-- Hoja "Tráfico" — Sesiones por referrer y canal, CO + MX
-- Source: {co,mx}_segment_profiles.pages
--
-- ═══ SESIONES, NO COSECHAS ═══
-- Esta hoja mide TRÁFICO: volumen de visitas incluyendo a quien vuelve. Es distinto de
-- la hoja "Funnel WEB", que usa cosechas (cada visitante cuenta UNA vez, en su primera
-- sesión). Acá un recurrente suma una sesión cada vez que vuelve.
--
-- Definición de sesión: eventos del mismo `anonymous_id` separados por menos de 30
-- minutos de inactividad. Segment no trae session_id, así que se reconstruye con el
-- corte de 30 min (el estándar de la industria).
--
-- ⚠️ `anonymous_id` es una COOKIE DE NAVEGADOR, no una persona. Celular + computador =
--    dos visitantes; borrar cookies = visitante nuevo. "Recurrente" significa
--    "mismo navegador que ya había venido", no "misma persona".
--
-- Atribución POR SESIÓN (no por persona): se toma el referrer y el utm_campaign del
-- PRIMER evento de cada sesión. Así una misma persona que llega hoy por Google Ads y
-- mañana directo, cuenta una sesión en cada canal — que es como se lee el tráfico.

WITH ev AS (
  SELECT 'MX' AS pais, anonymous_id, timestamp AS ts,
         DATE(timestamp, 'America/Mexico_City') AS d,
         LOWER(IFNULL(context_page_referrer, '')) AS ref,
         LOWER(REGEXP_EXTRACT(context_page_url, r'[?&]utm_campaign=([^&#]*)')) AS camp
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Mexico_City') >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
    AND DATE(timestamp, 'America/Mexico_City') < CURRENT_DATE()
    AND context_page_url LIKE '%habi.mx%' AND anonymous_id IS NOT NULL
  UNION ALL
  SELECT 'CO', anonymous_id, timestamp,
         DATE(timestamp, 'America/Bogota'),
         LOWER(IFNULL(context_page_referrer, '')),
         LOWER(REGEXP_EXTRACT(context_page_url, r'[?&]utm_campaign=([^&#]*)'))
  FROM `sellers-main-prod.co_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Bogota') >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
    AND DATE(timestamp, 'America/Bogota') < CURRENT_DATE()
    AND context_page_url LIKE '%habi.co%' AND anonymous_id IS NOT NULL
),

-- corte de sesión: >30 min de inactividad abre una sesión nueva
marcado AS (
  SELECT *,
    IF(TIMESTAMP_DIFF(ts, LAG(ts) OVER (PARTITION BY pais, anonymous_id ORDER BY ts), MINUTE) > 30
       OR LAG(ts) OVER (PARTITION BY pais, anonymous_id ORDER BY ts) IS NULL, 1, 0) AS inicia
  FROM ev
),
sesionado AS (
  SELECT *, SUM(inicia) OVER (PARTITION BY pais, anonymous_id ORDER BY ts
                              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS sid
  FROM marcado
),

-- una fila por sesión, con el referrer y la campaña de su primer evento
sesion AS (
  SELECT pais, anonymous_id, sid, d, ref, camp,
         MIN(ts) OVER (PARTITION BY pais, anonymous_id ORDER BY ts) AS primera_ts
  FROM sesionado
  QUALIFY ROW_NUMBER() OVER (PARTITION BY pais, anonymous_id, sid ORDER BY ts) = 1
),

-- ¿es la primera sesión de ese navegador en toda la ventana?
tipo_visita AS (
  SELECT *, IF(ROW_NUMBER() OVER (PARTITION BY pais, anonymous_id ORDER BY d, sid) = 1,
               'nueva', 'recurrente') AS visita
  FROM sesion
),

dic AS (
  SELECT 'CO' AS pais, LOWER(campana_mercadeo_original) AS c, mkt_channel_medium AS medium, mkt_platform AS plat
  FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia` WHERE campana_mercadeo_original IS NOT NULL
  UNION ALL
  SELECT 'MX', LOWER(campana_mercadeo_original), mkt_channel_medium, mkt_platform
  FROM `sellers-main-prod.bi_mx.registro_unico_utm_mkt_mexico` WHERE campana_mercadeo_original IS NOT NULL
),
dic1 AS (SELECT * FROM dic QUALIFY ROW_NUMBER() OVER (PARTITION BY pais, c ORDER BY plat) = 1),

clasificado AS (
  SELECT t.pais, t.d, t.visita,
    CASE
      WHEN t.ref = '' THEN '(directo / sin referrer)'
      ELSE REGEXP_REPLACE(IFNULL(REGEXP_EXTRACT(t.ref, r'^https?://([^/:?#]+)'), '(referrer ilegible)'),
                          r'^(www|m|l)\.', '')
    END AS host,
    -- mismo criterio de canal que la hoja de funnel: diccionario primero, referrer después
    CASE
      WHEN dd.plat IS NOT NULL THEN CONCAT(dd.plat, ' · ', dd.medium)
      WHEN t.camp IS NOT NULL THEN 'Pauta sin clasificar'
      WHEN t.ref = '' THEN 'Directo'
      WHEN REGEXP_CONTAINS(t.ref, r'^https?://([^/:?#]*\.)?(chatgpt\.com|openai\.com|perplexity\.ai|gemini\.google\.com|copilot\.microsoft\.com|claude\.ai|chat\.deepseek\.com)') THEN 'Buscador IA · Orgánico'
      WHEN REGEXP_CONTAINS(t.ref, r'^https?://([^/:?#]*\.)?google\.') OR STARTS_WITH(t.ref, 'https://syndicatedsearch.goog') THEN 'Google · Orgánico'
      WHEN REGEXP_CONTAINS(t.ref, r'^https?://([^/:?#]*\.)?(bing|yahoo|duckduckgo|ecosia|yandex)\.') THEN 'Otro buscador · Orgánico'
      WHEN REGEXP_CONTAINS(t.ref, r'^https?://([^/:?#]*\.)?(facebook|instagram)\.') THEN 'Meta · Orgánico'
      WHEN REGEXP_CONTAINS(t.ref, r'^https?://([^/:?#]*\.)?(tiktok|youtube|twitter|linkedin|pinterest)\.') THEN 'Otra red · Orgánico'
      WHEN REGEXP_CONTAINS(t.ref, r'^https?://([^/:?#]*\.)?(habi\.co|tuhabi\.mx|habi\.mx)') THEN 'Interno'
      ELSE 'Referral'
    END AS canal
  FROM tipo_visita t
  LEFT JOIN dic1 dd ON dd.pais = t.pais AND dd.c = t.camp
),

tipado AS (
  SELECT *,
    CASE
      WHEN host = '(directo / sin referrer)' THEN 'Directo'
      WHEN REGEXP_CONTAINS(host, r'^(chatgpt\.com|openai\.com|perplexity\.ai|gemini\.google\.com|copilot\.microsoft\.com|claude\.ai|chat\.deepseek\.com|you\.com|poe\.com|grok\.com)$') THEN 'Buscador IA'
      WHEN REGEXP_CONTAINS(host, r'(^|\.)google\.') OR host = 'syndicatedsearch.goog' THEN 'Buscador'
      WHEN REGEXP_CONTAINS(host, r'(^|\.)(bing|yahoo|duckduckgo|ecosia|yandex)\.') THEN 'Buscador'
      WHEN REGEXP_CONTAINS(host, r'(^|\.)(facebook|instagram|tiktok|youtube|twitter|linkedin|pinterest|threads)\.') THEN 'Social'
      WHEN REGEXP_CONTAINS(host, r'(^|\.)(habi\.co|tuhabi\.mx|habi\.mx)$') OR REGEXP_CONTAINS(host, r'ampproject\.org$') THEN 'Interno'
      WHEN REGEXP_CONTAINS(host, r'(^|\.)(outlook|mail\.google|gmail|mail\.yahoo)\.') THEN 'Correo'
      ELSE 'Referral'
    END AS tipo
  FROM clasificado
),

expandido AS (
  SELECT pais, host, tipo, canal, visita, gran,
    CASE gran
      WHEN 'D' THEN d WHEN 'W' THEN DATE_TRUNC(d, ISOWEEK) WHEN 'C' THEN DATE_TRUNC(d, WEEK(WEDNESDAY))
      WHEN 'M' THEN DATE_TRUNC(d, MONTH) WHEN 'Q' THEN DATE_TRUNC(d, QUARTER) WHEN 'Y' THEN DATE_TRUNC(d, YEAR)
    END AS periodo
  FROM tipado, UNNEST(['D','W','C','M','Q','Y']) AS gran
),

agg AS (
  SELECT pais, gran, periodo, host, tipo, canal,
         COUNT(*) AS sesiones,
         COUNTIF(visita = 'nueva') AS sesiones_nuevas
  FROM expandido GROUP BY 1,2,3,4,5,6
),
recientes AS (
  SELECT * FROM agg QUALIFY DENSE_RANK() OVER (PARTITION BY pais, gran ORDER BY periodo DESC) <= 20
),
ranking AS (
  SELECT pais, gran, host, SUM(sesiones) tot,
         ROW_NUMBER() OVER (PARTITION BY pais, gran ORDER BY SUM(sesiones) DESC) rk
  FROM recientes GROUP BY 1,2,3
)

SELECT r.pais, r.gran,
  CASE r.gran
    WHEN 'M' THEN FORMAT_DATE('%Y-%m', r.periodo)
    WHEN 'Q' THEN CONCAT(FORMAT_DATE('%Y', r.periodo), '-Q', CAST(EXTRACT(QUARTER FROM r.periodo) AS STRING))
    WHEN 'Y' THEN FORMAT_DATE('%Y', r.periodo)
    ELSE CAST(r.periodo AS STRING)
  END AS periodo,
  -- los buscadores de IA se fuerzan siempre: jamás entrarían al top 30 y el punto de
  -- la tabla es poder detectarlos temprano
  IF(k.rk <= 30 OR r.tipo = 'Buscador IA', r.host, '(otros referrers)') AS host,
  IF(k.rk <= 30 OR r.tipo = 'Buscador IA', r.tipo, 'Referral') AS tipo,
  r.canal,
  SUM(r.sesiones) AS sesiones,
  SUM(r.sesiones_nuevas) AS sesiones_nuevas
FROM recientes r
JOIN ranking k ON k.pais = r.pais AND k.gran = r.gran AND k.host = r.host
GROUP BY 1,2,3,4,5,6
ORDER BY pais, gran, periodo, sesiones DESC
