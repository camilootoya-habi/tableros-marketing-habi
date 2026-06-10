-- WBR 2.0 — Métricas diarias por fuente (MX)
-- Output: one row per (day, fuente) with reg, cal, asg, spend.
-- Window: últimas 20 semanas ISO (lun-dom), excluye semana actual.
-- Volumes are EVENT-based (each metric counted in the day it happened).
-- Notas MX vs CO:
--   - TIG MX usa `id_negocio` (no `negocio_id`)
--   - history_state MX: tabla `mx_rds_staging.habi_db_history_state` con cols `deal_id`, `state_id`, `date_create`
--   - state_id IN (20, 63) = calificado (mismo significado que CO)
--   - fuente_id set MX: 3, 7, 35, 39, 46, 47 (46=Propiedades en vez de 20=CRM)
--   - canal_adquisicion en spend MX: solo 'Web' / 'Lead Form' / 'Whats App' / 'Otro'

WITH
  leads AS (
    SELECT g.id_negocio AS negocio_id, g.fuente_id, DATE(g.fecha_creacion) AS reg_date
    FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
    WHERE g.fuente_id IN (3, 7, 35, 39, 46, 47)
  ),
  cal AS (
    SELECT deal_id AS negocio_id, MIN(date_create) AS cal_ts
    FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
    WHERE state_id IN (20, 63)
    GROUP BY 1
    HAVING MIN(date_create) >= DATE_SUB(CURRENT_DATE(), INTERVAL 175 DAY)
      AND MIN(date_create) < CURRENT_DATE()
  ),
  reg_agg AS (
    SELECT reg_date AS day, fuente_id, COUNT(*) AS n
    FROM leads
    WHERE reg_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 175 DAY)
      AND reg_date < CURRENT_DATE()
    GROUP BY 1, 2
  ),
  cal_agg AS (
    SELECT DATE(c.cal_ts) AS day, l.fuente_id, COUNT(*) AS n
    FROM cal c
    JOIN leads l ON l.negocio_id = c.negocio_id
    GROUP BY 1, 2
  ),
  asg_agg AS (
    SELECT a.dia AS day, a.fuente_id_tig AS fuente_id, COUNT(*) AS n
    FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` a
    WHERE a.pais = 'mexico'
      AND a.fuente_id_tig IN (3, 7, 35, 39, 46, 47)
      AND a.dia >= DATE_SUB(CURRENT_DATE(), INTERVAL 175 DAY)
      AND a.dia < CURRENT_DATE()
    GROUP BY 1, 2
  ),
  -- Spend mapped to fuente via canal_adquisicion (limitado en MX: solo Web y Lead Form tienen mapeo claro)
  spend_agg AS (
    SELECT
      i.date AS day,
      CASE
        WHEN i.canal_adquisicion = 'Web' THEN 3
        WHEN i.canal_adquisicion = 'Lead Form' THEN 47
      END AS fuente_id,
      ROUND(SUM(i.spend), 0) AS spend
    FROM `papyrus-data-mx.habi_wh_bi.resumen_inversiones_mkt_mx` i
    WHERE i.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 175 DAY)
      AND i.date < CURRENT_DATE()
    GROUP BY 1, 2
    HAVING fuente_id IS NOT NULL
  ),
  weeks_fuentes AS (
    SELECT day, fuente_id FROM reg_agg
    UNION DISTINCT SELECT day, fuente_id FROM cal_agg
    UNION DISTINCT SELECT day, fuente_id FROM asg_agg
    UNION DISTINCT SELECT day, fuente_id FROM spend_agg
  )

SELECT
  CAST(wf.day AS STRING) AS day,
  CASE wf.fuente_id
    WHEN 3  THEN 'WEB'
    WHEN 7  THEN 'Estudio Inmueble'
    WHEN 35 THEN 'Comercial'
    WHEN 39 THEN 'Broker'
    WHEN 46 THEN 'Propiedades'
    WHEN 47 THEN 'lead_forms'
  END AS fuente,
  COALESCE(r.n, 0)        AS reg,
  COALESCE(c.n, 0)        AS cal,
  COALESCE(a.n, 0)        AS asg,
  COALESCE(s.spend, NULL) AS spend
FROM weeks_fuentes wf
LEFT JOIN reg_agg   r USING (day, fuente_id)
LEFT JOIN cal_agg   c USING (day, fuente_id)
LEFT JOIN asg_agg   a USING (day, fuente_id)
LEFT JOIN spend_agg s USING (day, fuente_id)
ORDER BY day, fuente
