-- WBR 2.0 — Métricas diarias por canal (CO)
-- Output: one row per (day, channel, fuente) with reg, cal, asg, spend.
-- Window: últimas 20 semanas ISO (lun-dom), excluye semana actual.
-- Volumes are EVENT-based.

WITH
  utm_dedup AS (
    SELECT *
    FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
    QUALIFY ROW_NUMBER() OVER(PARTITION BY campana_mercadeo_original ORDER BY campana_mercadeo_original) = 1
  ),
  utm_dedup_camp AS (
    SELECT *
    FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
    QUALIFY ROW_NUMBER() OVER(PARTITION BY mkt_campaign_name ORDER BY mkt_campaign_name) = 1
  ),
  leads AS (
    SELECT
      g.nid, g.negocio_id, g.fuente, g.fuente_id,
      DATE(g.fecha_creacion) AS reg_date,
      CASE g.fuente_id
        WHEN 3  THEN 'WEB'
        WHEN 7  THEN 'Estudio Inmueble'
        WHEN 20 THEN 'CRM'
        WHEN 35 THEN 'Comercial'
        WHEN 39 THEN 'Broker'
        WHEN 47 THEN 'lead_forms'
      END AS fuente_canon,
      CASE
        WHEN g.fuente IN ('lead_forms', 'Lead Forms') THEN 'lead_forms'
        WHEN g.campana_mercadeo IS NULL OR g.campana_mercadeo = ''
          THEN CONCAT(g.fuente, ' Direct')
        WHEN m.mkt_channel_medium IS NULL OR m.mkt_channel_medium = ''
          THEN g.campana_mercadeo
        ELSE m.mkt_channel_medium
      END AS channel
    FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g
    LEFT JOIN utm_dedup m ON g.campana_mercadeo = m.campana_mercadeo_original
    WHERE g.fuente_id IN (3, 7, 20, 35, 39, 47)
      AND DATE(g.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 760 DAY)
  ),
  cal AS (
    SELECT negocio_id, MIN(fecha_actualizacion) AS cal_ts
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
    WHERE estado_id IN (20, 63)
    GROUP BY 1
    HAVING MIN(fecha_actualizacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
      AND MIN(fecha_actualizacion) < CURRENT_DATE()
  ),
  reg_agg AS (
    SELECT reg_date AS day, channel, fuente_canon AS fuente, COUNT(*) AS n
    FROM leads
    WHERE reg_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
      AND reg_date < CURRENT_DATE()
    GROUP BY 1, 2, 3
  ),
  cal_agg AS (
    SELECT DATE(c.cal_ts) AS day, l.channel, l.fuente_canon AS fuente, COUNT(*) AS n
    FROM cal c
    JOIN leads l ON l.negocio_id = c.negocio_id
    GROUP BY 1, 2, 3
  ),
  asg_agg AS (
    SELECT
      a.dia AS day,
      l.channel, l.fuente_canon AS fuente,
      COUNT(*) AS n
    FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` a
    JOIN leads l ON l.nid = a.nid
    WHERE a.pais = 'colombia'
      AND a.fuente_id_tig IN (3, 7, 20, 35, 39, 47)
      AND a.dia >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
      AND a.dia < CURRENT_DATE()
    GROUP BY 1, 2, 3
  ),
  spend_agg AS (
    SELECT
      i.date AS day,
      -- Collapse lead_forms Paid + Direct into single 'lead_forms' to match leads-side
      CASE
        WHEN m.mkt_channel_medium IN ('lead_forms Paid', 'lead_forms Direct') THEN 'lead_forms'
        ELSE m.mkt_channel_medium
      END AS channel,
      CASE
        WHEN m.mkt_channel_medium LIKE 'WEB%' THEN 'WEB'
        WHEN m.mkt_channel_medium LIKE 'Estudio Inmueble%' THEN 'Estudio Inmueble'
        WHEN m.mkt_channel_medium IN ('lead_forms Paid', 'lead_forms Direct') OR m.mkt_channel_medium LIKE 'Lead Forms%' THEN 'lead_forms'
      END AS fuente,
      ROUND(SUM(i.spend), 0)       AS spend,
      ROUND(SUM(i.clicks), 0)      AS clicks,
      ROUND(SUM(i.impressions), 0) AS impressions
    FROM `papyrus-data.habi_wh_bi.resumen_inversiones_mkt_co` i
    LEFT JOIN utm_dedup_camp m ON i.campana = m.mkt_campaign_name
    WHERE i.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
      AND i.date < CURRENT_DATE()
      AND m.mkt_channel_medium IS NOT NULL
    GROUP BY 1, 2, 3
    HAVING fuente IS NOT NULL
  ),
  weeks_channels AS (
    SELECT day, channel, fuente FROM reg_agg
    UNION DISTINCT SELECT day, channel, fuente FROM cal_agg
    UNION DISTINCT SELECT day, channel, fuente FROM asg_agg
    UNION DISTINCT SELECT day, channel, fuente FROM spend_agg
  )

SELECT
  CAST(wc.day AS STRING) AS day,
  wc.channel,
  wc.fuente,
  COALESCE(r.n, 0)              AS reg,
  COALESCE(c.n, 0)              AS cal,
  COALESCE(a.n, 0)              AS asg,
  COALESCE(s.spend, NULL)       AS spend,
  COALESCE(s.clicks, NULL)      AS clicks,
  COALESCE(s.impressions, NULL) AS impressions
FROM weeks_channels wc
LEFT JOIN reg_agg   r USING (day, channel, fuente)
LEFT JOIN cal_agg   c USING (day, channel, fuente)
LEFT JOIN asg_agg   a USING (day, channel, fuente)
LEFT JOIN spend_agg s USING (day, channel, fuente)
ORDER BY day, channel
