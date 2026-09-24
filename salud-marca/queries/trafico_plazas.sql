-- marca-mx/queries/trafico_plazas.sql
-- Usuarios activos GA4 por plaza × mes, cruzados con inversión mensual por área metropolitana.
-- CPV es mensual por diseño: la tabla de inversión no tiene granularidad diaria.
-- CDMX: GA4 separa CDMX de Estado de México, pero la inversión los agrupa en "Valle de México";
-- por eso el lado de GA4 también los une, o el CPV de CDMX saldría inflado.
-- pais en esta tabla viene como 'México' (no 'MX'): verificado con SELECT DISTINCT pais.
WITH ga AS (
  SELECT
    FORMAT_DATE('%Y-%m', PARSE_DATE('%Y%m%d', event_date)) AS month,
    CASE
      WHEN geo.region IN ('Nuevo Leon', 'Nuevo León') THEN 'MTY'
      WHEN geo.region = 'Jalisco'                     THEN 'GDL'
      WHEN geo.region IN ('Mexico City', 'Ciudad de Mexico', 'Ciudad de México',
                          'State of Mexico', 'Estado de Mexico', 'Estado de México') THEN 'CDMX'
      ELSE 'Resto'
    END AS plaza,
    user_pseudo_id
  FROM `papyrus-data-mx.analytics_325611813.events_*`
  WHERE _TABLE_SUFFIX >= '20240101'
),
usuarios AS (
  SELECT month, plaza, COUNT(DISTINCT user_pseudo_id) AS users
  FROM ga GROUP BY 1, 2
),
inv AS (
  SELECT
    FORMAT_DATE('%Y-%m', mes) AS month,
    CASE
      WHEN area_metropolitana = 'Zona metropolitana Monterrey'   THEN 'MTY'
      WHEN area_metropolitana = 'Zona metropolitana Guadalajara' THEN 'GDL'
      WHEN area_metropolitana = 'Valle de México'                THEN 'CDMX'
      ELSE 'Resto'
    END AS plaza,
    SUM(spend) AS spend
  FROM `sellers-main-prod.bi_mx.resumen_inversiones_regiones_mexico`
  WHERE mes >= '2024-01-01' AND pais = 'México'
  GROUP BY 1, 2
)
SELECT u.month, u.plaza, u.users, i.spend
FROM usuarios u LEFT JOIN inv i USING (month, plaza)
ORDER BY u.month, u.plaza
