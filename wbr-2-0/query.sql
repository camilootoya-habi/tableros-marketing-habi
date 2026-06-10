-- WBR 2.0 — Métricas diarias por fuente (CO)
-- Output: one row per (day, fuente) with reg, cal, asg, spend.
-- Window: últimas 14 semanas ISO (lun-dom), excluye semana actual.
-- Volumes are EVENT-based (each metric counted in the day it happened).

WITH
  leads AS (
    SELECT g.negocio_id, g.fuente_id, DATE(g.fecha_creacion) AS reg_date, g.last_estado_id
    FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g
    WHERE g.fuente_id IN (3, 7, 20, 35, 39, 47)
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
    SELECT reg_date AS day, fuente_id, COUNT(*) AS n
    FROM leads
    WHERE reg_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
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
    WHERE a.pais = 'colombia'
      AND a.fuente_id_tig IN (3, 7, 20, 35, 39, 47)
      AND a.dia >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
      AND a.dia < CURRENT_DATE()
    GROUP BY 1, 2
  ),
  -- completos (lead_forms): leads que YA NO están incompletos (estado actual ≠ 7/39), por fecha
  -- de registro. Es un ESTADO del lead, no un evento limpio; pero el completado ocurre a las horas
  -- del registro, así que en la práctica no cambia tras cerrar la semana.
  completos_agg AS (
    SELECT l.reg_date AS day, l.fuente_id, COUNTIF(l.last_estado_id NOT IN (7, 39)) AS completos
    FROM leads l
    WHERE l.reg_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY) AND l.reg_date < CURRENT_DATE()
    GROUP BY 1, 2
  ),
  -- Estudio Inmueble: paso por 65 contado por fecha de ENTRADA a 65 (evento); de esos, los calificados.
  ev_65 AS (
    SELECT negocio_id, MIN(fecha_actualizacion) AS ts
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
    WHERE estado_id = 65
    GROUP BY 1
  ),
  calif_ever AS (
    SELECT DISTINCT negocio_id
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
    WHERE estado_id IN (20, 63)
  ),
  paso65_agg AS (
    SELECT DATE(e.ts) AS day, l.fuente_id,
      COUNT(*)                            AS paso65,
      COUNTIF(c.negocio_id IS NOT NULL)   AS paso65_calif
    FROM ev_65 e JOIN leads l ON l.negocio_id = e.negocio_id
    LEFT JOIN calif_ever c ON c.negocio_id = e.negocio_id
    WHERE DATE(e.ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY) AND DATE(e.ts) < CURRENT_DATE()
    GROUP BY 1, 2
  ),
  -- Spend mapped to fuente via canal_adquisicion (Brand/Otro dropped → no fuente)
  spend_agg AS (
    SELECT
      i.date AS day,
      CASE
        WHEN i.canal_adquisicion = 'Web' THEN 3
        WHEN i.canal_adquisicion IN ('Habimetro', 'Calculadora de gastos') THEN 7
        WHEN i.canal_adquisicion = 'Lead Form' THEN 47
      END AS fuente_id,
      ROUND(SUM(i.spend), 0) AS spend
    FROM `papyrus-data.habi_wh_bi.resumen_inversiones_mkt_co` i
    WHERE i.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 600 DAY)
      AND i.date < CURRENT_DATE()
    GROUP BY 1, 2
    HAVING fuente_id IS NOT NULL
  ),
  weeks_fuentes AS (
    SELECT day, fuente_id FROM reg_agg
    UNION DISTINCT SELECT day, fuente_id FROM cal_agg
    UNION DISTINCT SELECT day, fuente_id FROM asg_agg
    UNION DISTINCT SELECT day, fuente_id FROM spend_agg
    UNION DISTINCT SELECT day, fuente_id FROM completos_agg
    UNION DISTINCT SELECT day, fuente_id FROM paso65_agg
  )

SELECT
  CAST(wf.day AS STRING) AS day,
  CASE wf.fuente_id
    WHEN 3  THEN 'WEB'
    WHEN 7  THEN 'Estudio Inmueble'
    WHEN 20 THEN 'CRM'
    WHEN 35 THEN 'Comercial'
    WHEN 39 THEN 'Broker'
    WHEN 47 THEN 'lead_forms'
  END AS fuente,
  COALESCE(r.n, 0)            AS reg,
  COALESCE(c.n, 0)            AS cal,
  COALESCE(a.n, 0)            AS asg,
  COALESCE(s.spend, NULL)     AS spend,
  COALESCE(ec.completos, 0)     AS completos,
  COALESCE(e65.paso65, 0)       AS paso65,
  COALESCE(e65.paso65_calif, 0) AS paso65_calif
FROM weeks_fuentes wf
LEFT JOIN reg_agg      r   USING (day, fuente_id)
LEFT JOIN cal_agg      c   USING (day, fuente_id)
LEFT JOIN asg_agg      a   USING (day, fuente_id)
LEFT JOIN spend_agg    s   USING (day, fuente_id)
LEFT JOIN completos_agg ec USING (day, fuente_id)
LEFT JOIN paso65_agg   e65 USING (day, fuente_id)
ORDER BY day, fuente
