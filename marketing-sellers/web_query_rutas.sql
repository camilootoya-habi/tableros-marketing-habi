-- Hoja "Funnel WEB" — Recorridos reales dentro del formulario, CO + MX
-- Source: {co,mx}_segment_profiles.pages
--
-- Una fila por (país, granularidad, ruta) con el número de visitantes únicos que
-- siguieron esa secuencia de pasos. Solo el PERÍODO COMPLETO MÁS RECIENTE de cada
-- granularidad (se excluye el período en curso, que daría rutas truncadas).
--
-- La ruta colapsa repeticiones consecutivas del mismo paso (recargas de página),
-- pero SÍ conserva los retrocesos: `contacto → inicio` es un recorrido real y
-- distinto de `inicio → contacto`.
--
-- ⚠️ El orden de los pasos NO es el mismo en los dos países (medido 2026-09-02):
--    CO: direccion → zona → datos/confirmar → contacto → caracteristicas → detalles → fin
--    MX: inicio → confirmar → datos → zona → contacto → sugerencias → caract → detalles → fin

WITH ev AS (
  SELECT 'MX' AS pais, anonymous_id, timestamp AS ts,
         DATE(timestamp, 'America/Mexico_City') AS d, context_page_path AS path
  FROM `sellers-main-prod.mx_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Mexico_City') >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
    AND context_page_url LIKE '%habi.mx%' AND anonymous_id IS NOT NULL
    AND context_page_path LIKE '/formulario-inmueble%'
  UNION ALL
  SELECT 'CO', anonymous_id, timestamp,
         DATE(timestamp, 'America/Bogota'), context_page_path
  FROM `sellers-main-prod.co_segment_profiles.pages`
  WHERE DATE(timestamp, 'America/Bogota') >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
    AND context_page_url LIKE '%habi.co%' AND anonymous_id IS NOT NULL
    AND context_page_path LIKE '/formulario-inmueble%'
),

st AS (
  SELECT pais, anonymous_id, ts, d,
    CASE
      WHEN path = '/formulario-inmueble/inmuebles-zona'   THEN 'Zona'
      WHEN path = '/formulario-inmueble/datos-inmueble'   THEN 'Datos'
      WHEN path = '/formulario-inmueble/caracteristicas'  THEN 'Características'
      WHEN path = '/formulario-inmueble/ultimos-detalles' THEN 'Últimos detalles'
      WHEN path = '/formulario-inmueble/contacto'         THEN 'Contacto'
      WHEN path = '/formulario-inmueble/felicitaciones'   THEN 'FIN'
      WHEN pais = 'MX' AND path = '/formulario-inmueble/inicio'    THEN 'Inicio'
      WHEN pais = 'CO' AND path = '/formulario-inmueble/direccion' THEN 'Inicio'
      WHEN pais = 'MX' AND path = '/formulario-inmueble/confirmar-ubicacion-mx' THEN 'Ubicación'
      WHEN pais = 'CO' AND path = '/formulario-inmueble/confirmar-ubicacion'    THEN 'Ubicación'
      WHEN pais = 'MX' AND path IN ('/formulario-inmueble/sugerencias-de-propiedades',
                                    '/formulario-inmueble/editar-sugerencias') THEN 'Sugerencias'
      WHEN pais = 'CO' AND path = '/formulario-inmueble/sugerencias' THEN 'Sugerencias'
      ELSE NULL
    END AS s
  FROM ev
),

-- una fila por (visitante, granularidad): la ruta se arma DENTRO del período
expanded AS (
  SELECT pais, anonymous_id, ts, d, s, gran,
    CASE gran
      WHEN 'D' THEN d WHEN 'W' THEN DATE_TRUNC(d, ISOWEEK) WHEN 'C' THEN DATE_TRUNC(d, WEEK(WEDNESDAY))
      WHEN 'M' THEN DATE_TRUNC(d, MONTH) WHEN 'Q' THEN DATE_TRUNC(d, QUARTER) WHEN 'Y' THEN DATE_TRUNC(d, YEAR)
    END AS periodo
  FROM st, UNNEST(['D','W','C','M','Q','Y']) AS gran
  WHERE s IS NOT NULL
),

-- último período CERRADO de cada granularidad (el en curso daría rutas truncadas)
ultimo AS (
  SELECT gran, MAX(periodo) AS periodo FROM expanded
  WHERE periodo < CASE gran
      WHEN 'D' THEN CURRENT_DATE() WHEN 'W' THEN DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
      WHEN 'C' THEN DATE_TRUNC(CURRENT_DATE(), WEEK(WEDNESDAY)) WHEN 'M' THEN DATE_TRUNC(CURRENT_DATE(), MONTH)
      WHEN 'Q' THEN DATE_TRUNC(CURRENT_DATE(), QUARTER) WHEN 'Y' THEN DATE_TRUNC(CURRENT_DATE(), YEAR)
    END
  GROUP BY gran
),

seq AS (
  SELECT e.pais, e.gran, e.periodo, e.anonymous_id,
         ARRAY_AGG(e.s ORDER BY e.ts) AS pasos,
         -- ⚠️ fechas LOCALES, no DATE(timestamp): DATE() sobre un TIMESTAMP evalúa en UTC
         -- y una visita de las 22:00 CDMX caería al día siguiente, corriendo la ventana
         -- del join de leads un día completo (bug detectado 2026-09-02).
         MIN(e.d) AS d0, MAX(e.d) AS d1
  FROM expanded e JOIN ultimo u ON u.gran = e.gran AND u.periodo = e.periodo
  GROUP BY 1,2,3,4
),

-- ¿ese visitante llegó a crear lead? El lead se crea al pasar el OTP (medido
-- 2026-09-02: 100% de quien valida obtiene lead, ~110s después; solo 33% de
-- quien NO valida). Se ancla el select_content al MISMO DÍA de la visita para no
-- arrastrar sesiones viejas (gotcha del chain UUID, ver docs/marketing/puentes-datos-web.md).
sc AS (
  SELECT 'MX' AS pais, anonymous_id, backbone_uuid, DATE(timestamp,'America/Mexico_City') AS d
  FROM `sellers-main-prod.mx_segment_profiles.select_content`
  WHERE DATE(timestamp,'America/Mexico_City') >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
    AND backbone_uuid IS NOT NULL
  UNION ALL
  SELECT 'CO', anonymous_id, backbone_uuid, DATE(timestamp,'America/Bogota')
  FROM `sellers-main-prod.co_segment_profiles.select_content`
  WHERE DATE(timestamp,'America/Bogota') >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
    AND backbone_uuid IS NOT NULL
),
br AS (
  SELECT uuid, deal_uuid FROM `sellers-main-prod.top_funnel.web_global_api_business`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY uuid ORDER BY deal_uuid) = 1
),
deals AS (
  SELECT 'MX' AS pais, uuid, nid, DATE(date_create) AS d_deal FROM `sellers-main-prod.mx_rds_staging.habi_db_property_deal` WHERE nid IS NOT NULL
  UNION ALL
  SELECT 'CO', uuid, nid, DATE(fecha_creacion) FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` WHERE nid IS NOT NULL
),
con_lead AS (
  SELECT DISTINCT sc.pais, sc.anonymous_id, sc.d, dl.d_deal
  FROM sc
  JOIN br ON br.uuid = sc.backbone_uuid
  JOIN deals dl ON dl.uuid = br.deal_uuid AND dl.pais = sc.pais
),

-- colapsa repeticiones consecutivas (recargas), conserva retrocesos
rutas AS (
  SELECT s.pais, s.gran, s.periodo, s.anonymous_id,
    (cl.anonymous_id IS NOT NULL) AS creo_lead,
    ARRAY_TO_STRING(ARRAY(
      SELECT p FROM UNNEST(pasos) p WITH OFFSET o
      WHERE o = 0 OR p != pasos[OFFSET(o-1)]
    ), ' → ') AS ruta,
    ARRAY_LENGTH(ARRAY(
      SELECT p FROM UNNEST(pasos) p WITH OFFSET o
      WHERE o = 0 OR p != pasos[OFFSET(o-1)]
    )) AS pasos_n
  FROM seq s
  LEFT JOIN con_lead cl
    ON cl.pais = s.pais AND cl.anonymous_id = s.anonymous_id
   AND cl.d BETWEEN s.d0 AND s.d1
   -- el DEAL además debe haberse creado dentro del recorrido: así "crea lead" significa
   -- "generó un negocio nuevo acá", no "esta persona tiene un negocio en algún lado".
   -- Medido 2026-09-02: hoy no cambia ni un caso, pero blinda la definición.
   AND cl.d_deal BETWEEN s.d0 AND s.d1
),

agg AS (
  SELECT pais, gran, periodo, ruta,
         ANY_VALUE(pasos_n) AS pasos_n,
         COUNT(DISTINCT anonymous_id) AS visitantes,
         COUNT(DISTINCT IF(creo_lead, anonymous_id, NULL)) AS con_lead
  FROM rutas GROUP BY 1,2,3,4
)

SELECT pais, gran,
  CASE gran
    WHEN 'M' THEN FORMAT_DATE('%Y-%m', periodo)
    WHEN 'Q' THEN CONCAT(FORMAT_DATE('%Y', periodo), '-Q', CAST(EXTRACT(QUARTER FROM periodo) AS STRING))
    WHEN 'Y' THEN FORMAT_DATE('%Y', periodo)
    ELSE CAST(periodo AS STRING)
  END AS periodo,
  ruta, pasos_n, visitantes, con_lead,
  ENDS_WITH(ruta, 'FIN') AS termina_en_registro
FROM agg
-- top 40 rutas por período: la cola es larguísima y aporta poco
QUALIFY ROW_NUMBER() OVER (PARTITION BY pais, gran ORDER BY visitantes DESC) <= 40
ORDER BY pais, gran, visitantes DESC
