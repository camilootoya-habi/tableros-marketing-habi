-- WBR 2.0 — Distribución del tiempo Registro → Asignado (en HORAS) · MX. Ver query_delay.sql (CO).
WITH
  leads AS (
    SELECT g.id_negocio AS negocio_id, g.nid, g.fuente_id, DATETIME(g.fecha_creacion) AS reg_dt
    FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
    WHERE g.fuente_id IN (3, 7, 35, 39, 46, 47)
      AND DATE(g.fecha_creacion) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), ISOWEEK), INTERVAL 5 WEEK)
      AND DATE(g.fecha_creacion) <  DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
  ),
  calif AS (
    SELECT DISTINCT deal_id AS negocio_id
    FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
    WHERE state_id IN (20, 63)
  ),
  asg AS (
    SELECT nid, MIN(DATETIME(dia, hora)) AS asg_dt
    FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
    WHERE pais = 'mexico'
    GROUP BY 1
  ),
  j AS (
    SELECT
      CASE l.fuente_id WHEN 3 THEN 'WEB' WHEN 7 THEN 'Estudio Inmueble' WHEN 35 THEN 'Comercial'
                       WHEN 39 THEN 'Broker' WHEN 46 THEN 'Propiedades' WHEN 47 THEN 'lead_forms' END AS fuente,
      (cl.negocio_id IS NOT NULL) AS is_calif,
      DATETIME_DIFF(a.asg_dt, l.reg_dt, HOUR) AS d_h
    FROM leads l
    LEFT JOIN calif cl ON cl.negocio_id = l.negocio_id
    LEFT JOIN asg   a  ON a.nid = l.nid
  )
SELECT fuente, 'cohort' AS kind, 'all' AS bin, COUNT(*) AS n
FROM j WHERE fuente IS NOT NULL GROUP BY 1
UNION ALL
SELECT fuente, 'calif' AS kind, 'all' AS bin, COUNTIF(is_calif) AS n
FROM j WHERE fuente IS NOT NULL GROUP BY 1
UNION ALL
SELECT fuente, 'reg_asg' AS kind,
  CASE WHEN d_h < 6 THEN '0-6' WHEN d_h < 12 THEN '6-12' WHEN d_h < 18 THEN '12-18'
       WHEN d_h < 24 THEN '18-24' WHEN d_h < 30 THEN '24-30' WHEN d_h < 36 THEN '30-36'
       WHEN d_h < 42 THEN '36-42' WHEN d_h < 48 THEN '42-48' ELSE '48+' END AS bin,
  COUNT(*) AS n
FROM j WHERE fuente IS NOT NULL AND is_calif AND d_h >= 0
GROUP BY 1, 3
