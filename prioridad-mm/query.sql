-- Prioridad de gestión Market Maker — leads de marketing × tipificación A/B/C × asignación × fuente × área.
-- Últimas 18 semanas ISO completas (excluye la semana en curso).
--
-- Universo: leads de las 6 fuentes de marketing por país en `tabla_inmuebles_general`.
--   CO: WEB(3), Estudio Inmueble(7), CRM(20), Comercial(35), Broker(39), Lead Forms(47).
--   MX: WEB(3), Estudio Inmueble(7), Comercial(35), Broker(39), Propiedades(46), Lead Forms(47).
-- Bucketeo: ISO week por `fecha_creacion` del lead.
-- Tipificación: trae prioridad_gestion_market_maker del deal más reciente del mismo nid en hubspot.deals.
-- Asignación: flag = lead presente en sellers_leads_asignados_marketing_wbr_mart.
WITH co_leads AS (
  SELECT
    nid,
    DATE_TRUNC(DATE(fecha_creacion), ISOWEEK) AS semana,
    'Colombia' AS country,
    LOWER(fuente) AS fuente,
    fuente_id,
    area_metropolitana
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general`
  WHERE fuente_id IN (3, 7, 20, 35, 39, 47)
    AND DATE_TRUNC(DATE(fecha_creacion), ISOWEEK) >=
        DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 18 WEEK), ISOWEEK)
    AND DATE_TRUNC(DATE(fecha_creacion), ISOWEEK) <
        DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
),
mx_leads AS (
  SELECT
    nid,
    DATE_TRUNC(DATE(fecha_creacion), ISOWEEK) AS semana,
    'México' AS country,
    LOWER(fuente) AS fuente,
    fuente_id,
    area_metropolitana
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general`
  WHERE fuente_id IN (3, 7, 35, 39, 46, 47)
    AND DATE_TRUNC(DATE(fecha_creacion), ISOWEEK) >=
        DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 18 WEEK), ISOWEEK)
    AND DATE_TRUNC(DATE(fecha_creacion), ISOWEEK) <
        DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
),
leads AS (
  SELECT * FROM co_leads
  UNION ALL
  SELECT * FROM mx_leads
),
-- Deal más reciente por nid + país (evita duplicar leads con varios deals en HubSpot).
deals_dedup AS (
  SELECT nid, country, prioridad
  FROM (
    SELECT
      nid,
      country,
      prioridad_gestion_market_maker AS prioridad,
      ROW_NUMBER() OVER (PARTITION BY nid, country ORDER BY createdate DESC) AS rn
    FROM `sellers-main-prod.hubspot.deals`
    WHERE country IN ('Colombia','México')
  )
  WHERE rn = 1
),
asignados AS (
  SELECT DISTINCT nid, pais
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
),
enriched AS (
  SELECT
    l.semana,
    l.country,
    l.fuente,
    COALESCE(
      REGEXP_REPLACE(l.area_metropolitana, r'^[Zz]ona [Mm]etropolitana ', ''),
      'Sin clasificar'
    ) AS area,
    a.nid IS NOT NULL AS asignado,
    d.prioridad
  FROM leads l
  LEFT JOIN deals_dedup d
    ON l.nid = d.nid
   AND l.country = d.country
  LEFT JOIN asignados a
    ON l.nid = a.nid
   AND CASE l.country WHEN 'Colombia' THEN 'colombia' WHEN 'México' THEN 'mexico' END = a.pais
)
SELECT
  FORMAT_DATE('%Y-%m-%d', semana) AS semana,
  country,
  fuente,
  area,
  asignado,
  COUNTIF(prioridad = 'A') AS a,
  COUNTIF(prioridad = 'B') AS b,
  COUNTIF(prioridad = 'C') AS c,
  COUNTIF(prioridad IS NULL OR prioridad NOT IN ('A','B','C')) AS sin_tip,
  COUNT(*) AS n
FROM enriched
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 2, 3, 4, 5
