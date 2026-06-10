-- WBR 2.0 — Distribución del tiempo Registro → Asignado (en HORAS) · CO
-- Cohorte: leads registrados en las últimas 5 semanas ISO completas.
-- El % se calcula sobre el TOTAL DE CALIFICADOS de la cohorte (no sobre registros).
-- Output: filas (fuente, kind, bin, n):
--   kind='cohort' (bin='all') = leads registrados;  kind='calif' (bin='all') = leads calificados (denominador);
--   kind='reg_asg' = leads calificados Y asignados, por rango de 6h desde el registro (lag >= 0).
-- reg_ts = fecha_creacion (DATETIME); asg = DATETIME(dia, hora) del mart (misma zona, sin desfase).
WITH
  leads AS (
    SELECT g.negocio_id, g.nid, g.fuente_id, DATETIME(g.fecha_creacion) AS reg_dt
    FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g
    WHERE g.fuente_id IN (3, 7, 20, 35, 39, 47)
      AND DATE(g.fecha_creacion) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), ISOWEEK), INTERVAL 5 WEEK)
      AND DATE(g.fecha_creacion) <  DATE_TRUNC(CURRENT_DATE(), ISOWEEK)
  ),
  calif AS (
    SELECT DISTINCT negocio_id
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
    WHERE estado_id IN (20, 63)
  ),
  asg AS (
    SELECT nid, MIN(DATETIME(dia, hora)) AS asg_dt
    FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
    WHERE pais = 'colombia'
    GROUP BY 1
  ),
  j AS (
    SELECT
      CASE l.fuente_id WHEN 3 THEN 'WEB' WHEN 7 THEN 'Estudio Inmueble' WHEN 20 THEN 'CRM'
                       WHEN 35 THEN 'Comercial' WHEN 39 THEN 'Broker' WHEN 47 THEN 'lead_forms' END AS fuente,
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
