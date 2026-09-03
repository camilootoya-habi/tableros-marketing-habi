-- Hoja "Funnel WEB" — Sesiones por referrer, CO + MX, cosechas por granularidad
-- Source: {co,mx}_segment_profiles.pages
--
-- Una fila por (país, granularidad, período, host del referrer) con visitantes NUEVOS.
-- Misma lógica de cosecha que la tabla del funnel: el visitante se asigna al período de
-- su PRIMERA sesión, y el referrer es el de ese primer evento (no el de cualquier visita).
--
-- ⚠️ El host se extrae del referrer y se normaliza (se quitan `www.` y `m.`) para no
--    partir facebook.com / m.facebook.com en dos filas. Se matchea sobre el HOST, no
--    sobre la URL completa: matchear la URL entera mete falsos positivos (una URL de
--    habi.co con "gemini" en un parámetro se colaría como buscador de IA).
--
-- Los buscadores de IA se marcan aparte: hoy son marginales (ChatGPT ~115 visitantes en
-- CO y ~36 en MX en 180 días, Gemini 50/24) pero son el canal a vigilar.

WITH ev AS (
  SELECT 'MX' AS pais, anonymous_id, timestamp AS ts,
         DATE(timestamp, 'America/Mexico_City') AS d, LOWER(IFNULL(context_page_referrer, '')) AS ref
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Mexico_City') >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
    AND DATE(timestamp, 'America/Mexico_City') < CURRENT_DATE()
    AND context_page_url LIKE '%habi.mx%' AND anonymous_id IS NOT NULL
  UNION ALL
  SELECT 'CO', anonymous_id, timestamp,
         DATE(timestamp, 'America/Bogota'), LOWER(IFNULL(context_page_referrer, ''))
  FROM `sellers-main-prod.co_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Bogota') >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
    AND DATE(timestamp, 'America/Bogota') < CURRENT_DATE()
    AND context_page_url LIKE '%habi.co%' AND anonymous_id IS NOT NULL
),

-- cosecha = primera sesión del visitante; el referrer es el de ESE evento
primero AS (
  SELECT pais, anonymous_id, d AS cohorte, ref
  FROM ev
  QUALIFY ROW_NUMBER() OVER (PARTITION BY pais, anonymous_id ORDER BY ts) = 1
),

hosts AS (
  SELECT pais, anonymous_id, cohorte,
    CASE
      WHEN ref = '' THEN '(directo / sin referrer)'
      ELSE REGEXP_REPLACE(IFNULL(REGEXP_EXTRACT(ref, r'^https?://([^/:?#]+)'), '(referrer ilegible)'),
                          r'^(www|m|l)\.', '')
    END AS host
  FROM primero
),

clasificado AS (
  SELECT pais, anonymous_id, cohorte, host,
    CASE
      WHEN host = '(directo / sin referrer)' THEN 'Directo'
      WHEN REGEXP_CONTAINS(host, r'^(chatgpt\.com|.*\.openai\.com|openai\.com|perplexity\.ai|gemini\.google\.com|copilot\.microsoft\.com|claude\.ai|chat\.deepseek\.com|you\.com|poe\.com|grok\.com)$') THEN 'Buscador IA'
      WHEN REGEXP_CONTAINS(host, r'(^|\.)google\.') OR host = 'syndicatedsearch.goog' THEN 'Buscador'
      WHEN REGEXP_CONTAINS(host, r'(^|\.)(bing|yahoo|duckduckgo|ecosia|yandex)\.') THEN 'Buscador'
      WHEN REGEXP_CONTAINS(host, r'(^|\.)(facebook|instagram|tiktok|youtube|twitter|x|linkedin|pinterest|threads)\.') THEN 'Social'
      WHEN REGEXP_CONTAINS(host, r'(^|\.)(habi\.co|tuhabi\.mx|habi\.mx)$') OR REGEXP_CONTAINS(host, r'ampproject\.org$') THEN 'Interno'
      WHEN REGEXP_CONTAINS(host, r'(^|\.)(outlook|mail\.google|gmail|mail\.yahoo)\.') THEN 'Correo'
      ELSE 'Referral'
    END AS tipo
  FROM hosts
),

expandido AS (
  SELECT pais, host, tipo, gran,
    CASE gran
      WHEN 'D' THEN cohorte WHEN 'W' THEN DATE_TRUNC(cohorte, ISOWEEK) WHEN 'C' THEN DATE_TRUNC(cohorte, WEEK(WEDNESDAY))
      WHEN 'M' THEN DATE_TRUNC(cohorte, MONTH) WHEN 'Q' THEN DATE_TRUNC(cohorte, QUARTER) WHEN 'Y' THEN DATE_TRUNC(cohorte, YEAR)
    END AS periodo
  FROM clasificado, UNNEST(['D','W','C','M','Q','Y']) AS gran
),

agg AS (
  SELECT pais, gran, periodo, host, tipo, COUNT(*) AS sesiones
  FROM expandido GROUP BY 1,2,3,4,5
),

-- solo los 20 períodos que muestra la tabla
recientes AS (
  SELECT * FROM agg
  QUALIFY DENSE_RANK() OVER (PARTITION BY pais, gran ORDER BY periodo DESC) <= 20
),

-- top 30 hosts por país+granularidad sobre el total de esos períodos; el resto se agrupa.
-- ⚠️ Los buscadores de IA se fuerzan SIEMPRE, sin importar su volumen: hoy son decenas de
-- visitantes al mes y jamás entrarían al top 30, pero el punto de la tabla es poder ver si
-- empiezan a crecer. Agruparlos en "(otros referrers)" los haría invisibles justo cuando
-- interesa detectarlos temprano.
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
  IF(k.rk <= 30 OR r.tipo = 'Buscador IA', r.host, '(otros referrers)') AS host,
  IF(k.rk <= 30 OR r.tipo = 'Buscador IA', r.tipo, 'Referral') AS tipo,
  SUM(r.sesiones) AS sesiones
FROM recientes r
JOIN ranking k ON k.pais = r.pais AND k.gran = r.gran AND k.host = r.host
GROUP BY 1,2,3,4,5
ORDER BY pais, gran, periodo, sesiones DESC
