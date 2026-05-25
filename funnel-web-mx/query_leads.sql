-- Funnel Web MX — Leads (etapa 12)
-- Source: papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general (fuente_id=3)
-- Atribución: UTM dict via campana_mercadeo_original (chain segment no viable en MX, 1.7% coverage)

WITH leads AS (
  SELECT
    g.nid,
    DATE_TRUNC(DATE(g.fecha_creacion), ISOWEEK) AS week_start,
    g.ciudad,
    g.zona_grande_label,
    g.zona_mediana_label,
    g.campana_mercadeo
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
  WHERE g.fuente_id = 3
    AND g.fecha_creacion >= DATETIME(DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK))
    AND g.fecha_creacion < DATETIME(DATE_TRUNC(CURRENT_DATE(), ISOWEEK))
),
utm_dict AS (
  SELECT DISTINCT campana_mercadeo_original AS campana, mkt_channel_medium, mkt_platform
  FROM `sellers-main-prod.bi_mx.registro_unico_utm_mkt_mexico`
),
cal AS (
  SELECT deal_id, MIN(date_create) AS cal_ts
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
  WHERE state_id IN (20, 63)
  GROUP BY 1
),
deals_oltp AS (
  SELECT pd.nid, pd.id AS deal_id
  FROM `sellers-main-prod.mx_rds_staging.habi_db_property_deal` pd
  WHERE pd.nid IS NOT NULL
),
asg AS (
  SELECT DISTINCT a.nid
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` a
  WHERE a.pais = 'mexico' AND a.fuente_id_tig = 3
    AND a.dia >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 140 DAY), ISOWEEK)
    AND a.dia < DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
)
SELECT
  CAST(l.week_start AS STRING) AS week_start,
  CASE
    WHEN LOWER(IFNULL(ud.mkt_platform, '')) LIKE '%google%' AND LOWER(IFNULL(ud.mkt_channel_medium, '')) IN ('cpc','paid','paid search','paidsearch') THEN 'Google/Paid'
    WHEN LOWER(IFNULL(ud.mkt_platform, '')) LIKE '%google%' THEN 'Google/Organic'
    WHEN LOWER(IFNULL(ud.mkt_platform, '')) LIKE '%meta%' OR LOWER(IFNULL(ud.mkt_platform, '')) LIKE '%facebook%' OR LOWER(IFNULL(ud.mkt_platform, '')) LIKE '%instagram%' THEN 'Meta/Paid'
    WHEN LOWER(IFNULL(ud.mkt_platform, '')) LIKE '%bing%' THEN 'Bing/Paid'
    WHEN LOWER(IFNULL(ud.mkt_platform, '')) LIKE '%tiktok%' THEN 'TikTok/Paid'
    WHEN ud.mkt_platform IS NOT NULL AND ud.mkt_platform != '' THEN 'Otro/Otro'
    ELSE 'Direct/Direct'
  END AS canal_plat,
  'unknown' AS device,
  IFNULL(l.ciudad, 'Sin ciudad') AS ciudad,
  IFNULL(l.zona_grande_label, 'Sin zona grande') AS zona_grande,
  IFNULL(l.zona_mediana_label, 'Sin zona mediana') AS zona_mediana,
  COUNT(DISTINCT l.nid) AS n_leads,
  COUNT(DISTINCT IF(c.deal_id IS NOT NULL, l.nid, NULL)) AS n_calificados,
  COUNT(DISTINCT IF(asg.nid IS NOT NULL, l.nid, NULL)) AS n_asignados
FROM leads l
LEFT JOIN deals_oltp d ON d.nid = l.nid
LEFT JOIN cal c ON c.deal_id = d.deal_id
LEFT JOIN asg ON asg.nid = l.nid
LEFT JOIN utm_dict ud ON ud.campana = l.campana_mercadeo
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY 1, 2, 3, 4
