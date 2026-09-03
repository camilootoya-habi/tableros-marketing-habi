-- Hoja "Funnel WEB" — Cosechas por fecha de primera sesión, CO + MX, por granularidad
-- Source: {co,mx}_segment_profiles.pages
--
-- ═══ COSECHAS (cambio metodológico 2026-09-02) ═══
-- Cada visitante se asigna a UNA sola cosecha: el período de su PRIMERA sesión en el
-- sitio. Las etapas cuentan si ese visitante las alcanzó ALGUNA VEZ, sin importar
-- cuándo. Antes se contaban únicos por período, así que alguien que entraba el domingo
-- y llegaba a Contacto el lunes sumaba en dos columnas y la conversión no era directa.
-- Ahora todas las filas de una columna son LA MISMA GENTE → el % es conversión real.
--
-- Consecuencias que hay que tener presentes:
--   · `session` pasa a ser "visitantes NUEVOS del período" (primera vez que se les ve),
--     no "visitantes activos". Un recurrente se queda en su cosecha original.
--   · Las cosechas recientes MADURAN: alguien de ayer todavía puede convertir. El período
--     en curso siempre va a verse peor de lo que terminará. (La conversión es rápida —
--     el registro completo toma ~16 min — así que madura en horas, no semanas.)
--
-- ⚠️ Los pasos difieren por país (verificado a mano 2026-09-02: desde el home, CO abre
--    en /direccion y MX en /inicio). Ver docs/marketing/puentes-datos-web.md.
--
-- Ventana: 730 días. La tabla no está particionada: ampliarla no cuesta más (21,5 GB).

WITH evs AS (
  SELECT 'MX' AS pais, anonymous_id, DATE(timestamp, 'America/Mexico_City') AS d, timestamp AS ts,
         context_page_path AS path,
         LOWER(IFNULL(context_campaign_utm_source, '')) AS utm_source,
         LOWER(IFNULL(context_campaign_utm_medium, '')) AS utm_medium,
         context_user_agent_data_mobile AS is_mobile,
         LOWER(IFNULL(context_user_agent_data_platform, '')) AS ua_platform
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Mexico_City') >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
    AND DATE(timestamp, 'America/Mexico_City') < CURRENT_DATE()
    AND context_page_url LIKE '%habi.mx%' AND anonymous_id IS NOT NULL
  UNION ALL
  SELECT 'CO', anonymous_id, DATE(timestamp, 'America/Bogota'), timestamp,
         context_page_path,
         LOWER(IFNULL(context_campaign_utm_source, '')),
         LOWER(IFNULL(context_campaign_utm_medium, '')),
         context_user_agent_data_mobile,
         LOWER(IFNULL(context_user_agent_data_platform, ''))
  FROM `sellers-main-prod.co_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Bogota') >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
    AND DATE(timestamp, 'America/Bogota') < CURRENT_DATE()
    AND context_page_url LIKE '%habi.co%' AND anonymous_id IS NOT NULL
),

-- una fila por visitante: su cosecha (primera sesión), su atribución y qué etapas alcanzó
visitante AS (
  SELECT
    pais, anonymous_id,
    MIN(d) AS cohorte,
    ARRAY_AGG(STRUCT(utm_source, utm_medium, is_mobile, ua_platform) ORDER BY ts LIMIT 1)[OFFSET(0)] AS fe,
    MAX(IF(path = '/formulario-inmueble/inmuebles-zona', 1, 0))   AS zona,
    MAX(IF(path = '/formulario-inmueble/datos-inmueble', 1, 0))   AS datos_inmueble,
    MAX(IF(path = '/formulario-inmueble/caracteristicas', 1, 0))  AS caracteristicas,
    MAX(IF(path = '/formulario-inmueble/ultimos-detalles', 1, 0)) AS ultimos_detalles,
    MAX(IF(path = '/formulario-inmueble/contacto', 1, 0))         AS contacto,
    MAX(IF(path = '/formulario-inmueble/felicitaciones', 1, 0))   AS felicitaciones,
    MAX(IF(pais = 'MX' AND path = '/formulario-inmueble/inicio', 1,
        IF(pais = 'CO' AND path IN ('/formulario-inmueble/direccion','/formulario-inmueble/direccion/'), 1, 0))) AS form_top,
    MAX(IF(pais = 'MX' AND path = '/formulario-inmueble/confirmar-ubicacion-mx', 1,
        IF(pais = 'CO' AND path = '/formulario-inmueble/confirmar-ubicacion', 1, 0))) AS confirmar_ubicacion,
    MAX(IF(pais = 'MX' AND path IN ('/formulario-inmueble/sugerencias-de-propiedades','/formulario-inmueble/editar-sugerencias'), 1,
        IF(pais = 'CO' AND path = '/formulario-inmueble/sugerencias', 1, 0))) AS sugerencias
  FROM evs GROUP BY 1, 2
),

attr AS (
  SELECT pais, anonymous_id, cohorte,
    zona, datos_inmueble, caracteristicas, ultimos_detalles, contacto, felicitaciones,
    form_top, confirmar_ubicacion, sugerencias,
    CASE
      WHEN fe.utm_source LIKE '%google%' AND fe.utm_medium IN ('cpc','paid','ppc','paidsearch') THEN 'Google/Paid'
      WHEN fe.utm_source LIKE '%google%' THEN 'Google/Organic'
      WHEN fe.utm_source IN ('facebook','instagram','meta','fb','ig') AND fe.utm_medium IN ('cpc','paid','ppc','paid_social','paidsocial') THEN 'Meta/Paid'
      WHEN fe.utm_source IN ('facebook','instagram','meta','fb','ig') THEN 'Meta/Organic'
      WHEN fe.utm_source LIKE '%bing%' THEN 'Bing/Paid'
      WHEN fe.utm_source LIKE '%tiktok%' THEN 'TikTok/Paid'
      WHEN fe.utm_source = '' THEN 'Direct/Direct'
      ELSE 'Otro/Otro'
    END AS canal_plat,
    CASE
      WHEN fe.is_mobile = TRUE AND fe.ua_platform LIKE '%ipad%' THEN 'tablet'
      WHEN fe.is_mobile = TRUE THEN 'mobile'
      WHEN fe.is_mobile = FALSE THEN 'desktop'
      ELSE 'unknown'
    END AS device
  FROM visitante
),

-- una fila por (visitante, granularidad): el período sale de SU cosecha, no del evento
expandido AS (
  SELECT a.*, gran,
    CASE gran
      WHEN 'D' THEN cohorte WHEN 'W' THEN DATE_TRUNC(cohorte, ISOWEEK) WHEN 'C' THEN DATE_TRUNC(cohorte, WEEK(WEDNESDAY))
      WHEN 'M' THEN DATE_TRUNC(cohorte, MONTH) WHEN 'Q' THEN DATE_TRUNC(cohorte, QUARTER) WHEN 'Y' THEN DATE_TRUNC(cohorte, YEAR)
    END AS periodo
  FROM attr a, UNNEST(['D','W','C','M','Q','Y']) AS gran
),

agg AS (
  SELECT pais, gran, periodo, canal_plat, device, stage, n FROM expandido,
  UNNEST([
    STRUCT('session' AS stage, 1 AS n),
    ('form_top', form_top), ('zona', zona), ('confirmar_ubicacion', confirmar_ubicacion),
    ('datos_inmueble', datos_inmueble), ('caracteristicas', caracteristicas),
    ('ultimos_detalles', ultimos_detalles), ('sugerencias', sugerencias),
    ('contacto', contacto), ('felicitaciones', felicitaciones)
  ])
  WHERE n = 1
)

SELECT pais, gran,
  CASE gran
    WHEN 'M' THEN FORMAT_DATE('%Y-%m', periodo)
    WHEN 'Q' THEN CONCAT(FORMAT_DATE('%Y', periodo), '-Q', CAST(EXTRACT(QUARTER FROM periodo) AS STRING))
    WHEN 'Y' THEN FORMAT_DATE('%Y', periodo)
    ELSE CAST(periodo AS STRING)
  END AS periodo,
  stage, canal_plat, device, COUNT(*) AS n
FROM agg
GROUP BY 1, 2, 3, 4, 5, 6
QUALIFY DENSE_RANK() OVER (PARTITION BY pais, gran ORDER BY MIN(periodo) DESC) <= 20
ORDER BY pais, gran, periodo, stage
