-- WBR 2.0 — Métricas diarias por plataforma × canal × fuente (MX)
-- Plataforma viene de UTM dict (mkt_platform).
-- Output: one row per (day, platform, channel, fuente) with reg, cal, asg, spend.
-- Solo leads con UTM (los Direct/sin tracking no aparecen — no tienen platform).
-- Notas MX vs CO: ver query_mx.sql cabecera.

WITH
  utm_dedup AS (
    SELECT *
    FROM `sellers-main-prod.bi_mx.registro_unico_utm_mkt_mexico`
    QUALIFY ROW_NUMBER() OVER(PARTITION BY campana_mercadeo_original ORDER BY campana_mercadeo_original) = 1
  ),
  utm_dedup_camp AS (
    SELECT *
    FROM `sellers-main-prod.bi_mx.registro_unico_utm_mkt_mexico`
    QUALIFY ROW_NUMBER() OVER(PARTITION BY mkt_campaign_name ORDER BY mkt_campaign_name) = 1
  ),
  leads AS (
    SELECT
      g.nid, g.id_negocio AS negocio_id, g.fuente, g.fuente_id,
      DATE(g.fecha_creacion) AS reg_date,
      CASE g.fuente_id
        WHEN 3  THEN 'WEB'
        WHEN 7  THEN 'Estudio Inmueble'
        WHEN 35 THEN 'Comercial'
        WHEN 39 THEN 'Broker'
        WHEN 46 THEN 'Propiedades'
        WHEN 47 THEN 'lead_forms'
      END AS fuente_canon,
      CASE
        WHEN g.fuente IN ('lead_forms', 'Lead Forms') THEN 'lead_forms'
        WHEN m.mkt_channel_medium IS NULL OR m.mkt_channel_medium = ''
          THEN g.campana_mercadeo
        ELSE m.mkt_channel_medium
      END AS channel,
      m.mkt_platform AS platform
    FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
    JOIN utm_dedup m ON g.campana_mercadeo = m.campana_mercadeo_original
    WHERE g.fuente_id IN (3, 7, 35, 39, 46, 47)
      AND m.mkt_platform IS NOT NULL
      AND m.mkt_platform != ''
      AND DATE(g.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 760 DAY)
  ),
  cal AS (
    SELECT deal_id AS negocio_id, MIN(date_create) AS cal_ts
    FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
    WHERE state_id IN (20, 63)
    GROUP BY 1
    HAVING MIN(date_create) >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
      AND MIN(date_create) < CURRENT_DATE()
  ),
  reg_agg AS (
    SELECT reg_date AS day,
      platform, channel, fuente_canon AS fuente, COUNT(*) AS n
    FROM leads
    WHERE reg_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
      AND reg_date < CURRENT_DATE()
    GROUP BY 1, 2, 3, 4
  ),
  cal_agg AS (
    SELECT DATE(c.cal_ts) AS day,
      l.platform, l.channel, l.fuente_canon AS fuente, COUNT(*) AS n
    FROM cal c
    JOIN leads l ON l.negocio_id = c.negocio_id
    GROUP BY 1, 2, 3, 4
  ),
  asg_agg AS (
    SELECT a.dia AS day,
      l.platform, l.channel, l.fuente_canon AS fuente, COUNT(*) AS n
    FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` a
    JOIN leads l ON l.nid = a.nid
    WHERE a.pais = 'mexico'
      AND a.fuente_id_tig IN (3, 7, 35, 39, 46, 47)
      AND a.dia >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
      AND a.dia < CURRENT_DATE()
    GROUP BY 1, 2, 3, 4
  ),
  spend_agg AS (
    SELECT
      i.date AS day,
      m.mkt_platform AS platform,
      CASE
        WHEN m.mkt_channel_medium IN ('lead_forms Paid', 'lead_forms Direct', 'Lead Forms Paid') THEN 'lead_forms'
        ELSE m.mkt_channel_medium
      END AS channel,
      CASE
        WHEN m.mkt_channel_medium LIKE 'WEB%' THEN 'WEB'
        WHEN m.mkt_channel_medium LIKE 'Estudio Inmueble%' THEN 'Estudio Inmueble'
        WHEN m.mkt_channel_medium IN ('lead_forms Paid', 'lead_forms Direct') OR m.mkt_channel_medium LIKE 'Lead Forms%' THEN 'lead_forms'
        WHEN m.mkt_channel_medium LIKE 'Propiedades%' THEN 'Propiedades'
      END AS fuente,
      ROUND(SUM(i.spend), 0)       AS spend,
      ROUND(SUM(i.clicks), 0)      AS clicks,
      ROUND(SUM(i.impressions), 0) AS impressions
    FROM `papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx` i
    JOIN utm_dedup_camp m ON i.campana = m.mkt_campaign_name
    WHERE i.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
      AND i.date < CURRENT_DATE()
      AND m.mkt_channel_medium IS NOT NULL
      AND m.mkt_platform IS NOT NULL
      AND m.mkt_platform != ''
    GROUP BY 1, 2, 3, 4
    HAVING fuente IS NOT NULL
  ),
  weeks_combos AS (
    SELECT day, platform, channel, fuente FROM reg_agg
    UNION DISTINCT SELECT day, platform, channel, fuente FROM cal_agg
    UNION DISTINCT SELECT day, platform, channel, fuente FROM asg_agg
    UNION DISTINCT SELECT day, platform, channel, fuente FROM spend_agg
  )

SELECT
  CAST(wc.day AS STRING) AS day,
  wc.platform,
  wc.channel,
  wc.fuente,
  COALESCE(r.n, 0)              AS reg,
  COALESCE(c.n, 0)              AS cal,
  COALESCE(a.n, 0)              AS asg,
  COALESCE(s.spend, NULL)       AS spend,
  COALESCE(s.clicks, NULL)      AS clicks,
  COALESCE(s.impressions, NULL) AS impressions
FROM weeks_combos wc
LEFT JOIN reg_agg   r USING (day, platform, channel, fuente)
LEFT JOIN cal_agg   c USING (day, platform, channel, fuente)
LEFT JOIN asg_agg   a USING (day, platform, channel, fuente)
LEFT JOIN spend_agg s USING (day, platform, channel, fuente)
ORDER BY day, platform, channel
