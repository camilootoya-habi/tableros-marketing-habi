-- Hoja "Funnel WEB" — Leads / Calificados / Asignados, CO + MX, por granularidad
-- Source: papyrus-data{,-mx}.habi_wh_bi.tabla_inmuebles_general, fuente_id = 3 (WEB)
--
-- ⚠️ COUNT(DISTINCT nid) tampoco es sumable entre períodos → cada granularidad se
--    calcula en SQL (mismo motivo que en sessions).
-- ⚠️ Diferencias por país (ver docs/marketing/puentes-datos-web.md):
--    · proyecto GCP distinto: papyrus-data (CO) vs papyrus-data-mx (MX)
--    · zonas: CO usa `zona_grande`/`zona_mediana`; MX usa `*_label`
--    · calificado: CO histórico por negocio_id (= tni.id); MX history_state por deal_id
--    · el diccionario UTM es una TABLA EXTERNA sobre Google Sheets → requiere scope de
--      Drive (local: ~/bin/gcloud-login --enable-gdrive-access)

WITH leads AS (
  SELECT 'MX' AS pais, g.nid, DATE(g.fecha_creacion) AS d,
         g.ciudad, g.zona_grande_label AS zona_grande, g.zona_mediana_label AS zona_mediana, g.campana_mercadeo
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
  WHERE g.fuente_id = 3
    AND g.fecha_creacion >= DATETIME(DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY))
    AND g.fecha_creacion <  DATETIME(CURRENT_DATE())
  UNION ALL
  SELECT 'CO', g.nid, DATE(g.fecha_creacion),
         g.ciudad, g.zona_grande, g.zona_mediana, g.campana_mercadeo
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g
  WHERE g.fuente_id = 3
    AND g.fecha_creacion >= DATETIME(DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY))
    AND g.fecha_creacion <  DATETIME(CURRENT_DATE())
),
utm AS (
  SELECT DISTINCT pais, campana, mkt_channel_medium, mkt_platform FROM (
    SELECT 'MX' AS pais, campana_mercadeo_original AS campana, mkt_channel_medium, mkt_platform
    FROM `sellers-main-prod.bi_mx.registro_unico_utm_mkt_mexico`
    UNION ALL
    SELECT 'CO', campana_mercadeo_original, mkt_channel_medium, mkt_platform
    FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
  )
),
cal AS (
  SELECT 'MX' AS pais, pd.nid
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state` h
  JOIN `sellers-main-prod.mx_rds_staging.habi_db_property_deal` pd ON pd.id = h.deal_id
  WHERE h.state_id IN (20, 63) AND pd.nid IS NOT NULL GROUP BY 1,2
  UNION ALL
  SELECT 'CO', tni.nid
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2` h
  JOIN `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` tni ON tni.id = h.negocio_id
  WHERE h.estado_id IN (20, 63) AND tni.nid IS NOT NULL GROUP BY 1,2
),
asg AS (
  SELECT DISTINCT IF(a.pais = 'mexico', 'MX', 'CO') AS pais, a.nid
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` a
  WHERE a.pais IN ('mexico','colombia') AND a.fuente_id_tig = 3
    AND a.dia >= DATE_SUB(CURRENT_DATE(), INTERVAL 730 DAY)
),
enriched AS (
  SELECT l.pais, l.nid, l.d, l.ciudad, l.zona_grande, l.zona_mediana,
    CASE
      WHEN LOWER(IFNULL(u.mkt_platform,'')) LIKE '%google%' AND LOWER(IFNULL(u.mkt_channel_medium,'')) IN ('cpc','paid','paid search','paidsearch') THEN 'Google/Paid'
      WHEN LOWER(IFNULL(u.mkt_platform,'')) LIKE '%google%' THEN 'Google/Organic'
      WHEN LOWER(IFNULL(u.mkt_platform,'')) LIKE '%meta%' OR LOWER(IFNULL(u.mkt_platform,'')) LIKE '%facebook%' OR LOWER(IFNULL(u.mkt_platform,'')) LIKE '%instagram%' THEN 'Meta/Paid'
      WHEN LOWER(IFNULL(u.mkt_platform,'')) LIKE '%bing%' THEN 'Bing/Paid'
      WHEN LOWER(IFNULL(u.mkt_platform,'')) LIKE '%tiktok%' THEN 'TikTok/Paid'
      WHEN u.mkt_platform IS NOT NULL AND u.mkt_platform != '' THEN 'Otro/Otro'
      ELSE 'Direct/Direct'
    END AS canal_plat,
    IF(c.nid IS NOT NULL, 1, 0) AS es_calificado,
    IF(a.nid IS NOT NULL, 1, 0) AS es_asignado
  FROM leads l
  LEFT JOIN cal c ON c.nid = l.nid AND c.pais = l.pais
  LEFT JOIN asg a ON a.nid = l.nid AND a.pais = l.pais
  LEFT JOIN utm u ON u.campana = l.campana_mercadeo AND u.pais = l.pais
),
expanded AS (
  SELECT e.*, gran,
    CASE gran
      WHEN 'D' THEN e.d WHEN 'W' THEN DATE_TRUNC(e.d, ISOWEEK) WHEN 'C' THEN DATE_TRUNC(e.d, WEEK(WEDNESDAY))
      WHEN 'M' THEN DATE_TRUNC(e.d, MONTH) WHEN 'Q' THEN DATE_TRUNC(e.d, QUARTER) WHEN 'Y' THEN DATE_TRUNC(e.d, YEAR)
    END AS periodo
  FROM enriched e, UNNEST(['D','W','C','M','Q','Y']) AS gran
),
agg AS (
  SELECT pais, gran, periodo, canal_plat,
         IFNULL(ciudad,'Sin ciudad') AS ciudad,
         IFNULL(zona_grande,'Sin zona grande') AS zona_grande,
         IFNULL(zona_mediana,'Sin zona mediana') AS zona_mediana,
         COUNT(DISTINCT nid) AS n_leads,
         COUNT(DISTINCT IF(es_calificado = 1, nid, NULL)) AS n_calificados,
         COUNT(DISTINCT IF(es_asignado  = 1, nid, NULL)) AS n_asignados
  FROM expanded GROUP BY 1,2,3,4,5,6,7
)
SELECT pais, gran, CASE gran
         WHEN 'M' THEN FORMAT_DATE('%Y-%m', periodo)
         WHEN 'Q' THEN CONCAT(FORMAT_DATE('%Y', periodo), '-Q', CAST(EXTRACT(QUARTER FROM periodo) AS STRING))
         WHEN 'Y' THEN FORMAT_DATE('%Y', periodo)
         ELSE CAST(periodo AS STRING)
       END AS periodo, canal_plat, ciudad, zona_grande, zona_mediana,
       n_leads, n_calificados, n_asignados
FROM agg
QUALIFY DENSE_RANK() OVER (PARTITION BY pais, gran ORDER BY periodo DESC) <= 20
ORDER BY pais, gran, periodo
