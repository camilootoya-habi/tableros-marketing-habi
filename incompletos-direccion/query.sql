-- Funnel Incompletos / Revisar Dirección — CO + MX
-- Cohort por fecha_creacion. Para cada lead determinamos:
--   ever_inc   = pasó alguna vez por estado 7 (incompleto) o 39 (incompleto desde web). Se agrupan.
--   ever_rev   = pasó alguna vez por estado 3 (revisar dirección).
--   inc_to_20  = pasó por incompleto Y luego entró al estado 20 (calificado) en una transición posterior.
--   rev_to_20  = pasó por revisar dirección Y luego entró al estado 20.
--   cur_state  = estado actual (last_estado_id en CO, last_state_id en MX) en OLTP.
-- Salida por (g, c, f, p):
--   tr, t, inc_pass, inc_left, inc_to_20, rev_pass, rev_left, rev_to_20.
--
-- IDs de estado verificados en catálogos co_rds_staging.habi_db_tabla_estados y mx_rds_staging.habi_db_state.

WITH base AS (
  SELECT 'Colombia' AS c, tig.nid, tig.fuente_id, tig.fuente,
    DATE(tig.fecha_creacion) AS fecha, DATETIME(tig.fecha_creacion) AS fecha_ts, tig.negocio_id AS biz_id
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` tig
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 20, 35, 39, 47)

  UNION ALL

  SELECT 'México' AS c, tig.nid, tig.fuente_id, tig.fuente,
    DATE(tig.fecha_creacion) AS fecha, DATETIME(tig.fecha_creacion) AS fecha_ts, tig.id_negocio AS biz_id
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` tig
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente_id IN (3, 7, 35, 39, 46, 47)
),

-- Eventos del histórico (TODOS los estados, ambos países). Base para detectar entrada,
-- salida y "fin de estancia" en cada estado transitorio. next_ts = inicio del siguiente
-- evento = fin del segmento actual en ese estado.
ev AS (
  SELECT 'Colombia' c, negocio_id biz_id, estado_id st, DATETIME(fecha_actualizacion) ts
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
  WHERE negocio_id IS NOT NULL
  UNION ALL
  SELECT 'México', deal_id, state_id, DATETIME(date_create)
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state`
  WHERE deal_id IS NOT NULL
),
ev2 AS (
  SELECT c, biz_id, st, ts,
    LEAD(ts) OVER (PARTITION BY c, biz_id ORDER BY ts, st) AS next_ts
  FROM ev
),
-- Por lead: paso por cada estado, primera entrada, última entrada a 20, y "fin de estancia"
-- (rev_end / inc_end = último instante en que el lead seguía en el estado; 9999 si nunca salió).
-- El concepto TRAPPED (estuvo en el estado tras creacion+1h) se evalúa en `enriched` con fecha_ts.
historic AS (
  SELECT c, biz_id,
    MAX(IF(st IN (7, 39), 1, 0)) AS ever_inc,
    MAX(IF(st = 3, 1, 0)) AS ever_rev,
    MIN(IF(st IN (7, 39), ts, NULL)) AS first_inc,
    MIN(IF(st = 3, ts, NULL)) AS first_rev,
    MAX(IF(st IN (7, 39), IFNULL(next_ts, DATETIME '9999-12-31'), NULL)) AS inc_end,
    MAX(IF(st = 3, IFNULL(next_ts, DATETIME '9999-12-31'), NULL)) AS rev_end,
    MAX(IF(st = 20, ts, NULL)) AS last_20
  FROM ev2 GROUP BY c, biz_id
),

current_state AS (
  SELECT 'Colombia' AS c, id AS biz_id, last_estado_id AS st
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble`
  UNION ALL
  SELECT 'México' AS c, id AS biz_id, last_state_id AS st
  FROM `sellers-main-prod.mx_rds_staging.habi_db_property_deal`
),

-- Tipificación del call center (HubSpot, global). MAX ignora NULLs: si CUALQUIER deal del
-- nid tiene tipificación, se considera gestionado. NULL (o sin deal) = sin gestión.
tip AS (
  SELECT country AS c, nid, MAX(tipificacion_lead) AS tipificacion_lead
  FROM `sellers-main-prod.hubspot.deals`
  WHERE nid IS NOT NULL AND country IN ('Colombia', 'México')
  GROUP BY c, nid
),

enriched AS (
  SELECT b.c, b.nid, b.fuente_id, b.fuente, b.fecha,
    cs.st AS cur_state,
    IF(tp.tipificacion_lead IS NULL, 1, 0) AS no_tip,
    -- TRAPPED: el lead seguía en el estado DESPUÉS de creacion+1h (excluye el barrido
    -- automático del backbone, que entra y sale del estado en la primera hora).
    IF(h.ever_inc = 1 AND h.inc_end > DATETIME_ADD(b.fecha_ts, INTERVAL 1 HOUR), 1, 0) AS ever_inc,
    IF(h.ever_rev = 1 AND h.rev_end > DATETIME_ADD(b.fecha_ts, INTERVAL 1 HOUR), 1, 0) AS ever_rev,
    IF(h.ever_inc = 1 AND h.inc_end > DATETIME_ADD(b.fecha_ts, INTERVAL 1 HOUR)
       AND h.last_20 IS NOT NULL AND h.first_inc IS NOT NULL AND h.last_20 > h.first_inc, 1, 0) AS inc_to_20,
    IF(h.ever_rev = 1 AND h.rev_end > DATETIME_ADD(b.fecha_ts, INTERVAL 1 HOUR)
       AND h.last_20 IS NOT NULL AND h.first_rev IS NOT NULL AND h.last_20 > h.first_rev, 1, 0) AS rev_to_20
  FROM base b
  LEFT JOIN historic h ON h.c = b.c AND h.biz_id = b.biz_id
  LEFT JOIN current_state cs ON cs.c = b.c AND cs.biz_id = b.biz_id
  LEFT JOIN tip tp ON tp.c = b.c AND tp.nid = b.nid
),

day_periods AS (SELECT DISTINCT fecha FROM enriched ORDER BY fecha DESC LIMIT 120),
week_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, ISOWEEK) p FROM enriched ORDER BY p DESC LIMIT 25),
comm_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, WEEK(WEDNESDAY)) p FROM enriched ORDER BY p DESC LIMIT 25),
month_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, MONTH) p FROM enriched ORDER BY p DESC LIMIT 25),
quarter_periods AS (SELECT DISTINCT DATE_TRUNC(fecha, QUARTER) p FROM enriched ORDER BY p DESC LIMIT 25),

agg_daily AS (
  SELECT 'D' g, c, fuente_id f, ANY_VALUE(fuente) fn, CAST(fecha AS STRING) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(ever_inc = 1) inc_pass,
    COUNTIF(ever_inc = 1 AND (cur_state IS NULL OR cur_state NOT IN (7, 39))) inc_left,
    COUNTIF(inc_to_20 = 1) inc_to_20,
    COUNTIF(ever_rev = 1) rev_pass,
    COUNTIF(ever_rev = 1 AND (cur_state IS NULL OR cur_state != 3)) rev_left,
    COUNTIF(rev_to_20 = 1) rev_to_20,
    COUNTIF(ever_inc = 1 AND cur_state IN (7, 39) AND no_tip = 1) inc_reman_notip,
    COUNTIF(ever_rev = 1 AND cur_state = 3 AND no_tip = 1) rev_reman_notip
  FROM enriched WHERE fecha IN (SELECT fecha FROM day_periods) GROUP BY c, f, p
),
agg_weekly AS (
  SELECT 'W' g, c, fuente_id f, ANY_VALUE(fuente) fn, CAST(DATE_TRUNC(fecha, ISOWEEK) AS STRING) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(ever_inc = 1) inc_pass,
    COUNTIF(ever_inc = 1 AND (cur_state IS NULL OR cur_state NOT IN (7, 39))) inc_left,
    COUNTIF(inc_to_20 = 1) inc_to_20,
    COUNTIF(ever_rev = 1) rev_pass,
    COUNTIF(ever_rev = 1 AND (cur_state IS NULL OR cur_state != 3)) rev_left,
    COUNTIF(rev_to_20 = 1) rev_to_20,
    COUNTIF(ever_inc = 1 AND cur_state IN (7, 39) AND no_tip = 1) inc_reman_notip,
    COUNTIF(ever_rev = 1 AND cur_state = 3 AND no_tip = 1) rev_reman_notip
  FROM enriched WHERE DATE_TRUNC(fecha, ISOWEEK) IN (SELECT p FROM week_periods) GROUP BY c, f, p
),
agg_commercial AS (
  SELECT 'C' g, c, fuente_id f, ANY_VALUE(fuente) fn, CAST(DATE_TRUNC(fecha, WEEK(WEDNESDAY)) AS STRING) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(ever_inc = 1) inc_pass,
    COUNTIF(ever_inc = 1 AND (cur_state IS NULL OR cur_state NOT IN (7, 39))) inc_left,
    COUNTIF(inc_to_20 = 1) inc_to_20,
    COUNTIF(ever_rev = 1) rev_pass,
    COUNTIF(ever_rev = 1 AND (cur_state IS NULL OR cur_state != 3)) rev_left,
    COUNTIF(rev_to_20 = 1) rev_to_20,
    COUNTIF(ever_inc = 1 AND cur_state IN (7, 39) AND no_tip = 1) inc_reman_notip,
    COUNTIF(ever_rev = 1 AND cur_state = 3 AND no_tip = 1) rev_reman_notip
  FROM enriched WHERE DATE_TRUNC(fecha, WEEK(WEDNESDAY)) IN (SELECT p FROM comm_periods) GROUP BY c, f, p
),
agg_monthly AS (
  SELECT 'M' g, c, fuente_id f, ANY_VALUE(fuente) fn, FORMAT_DATE('%Y-%m', fecha) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(ever_inc = 1) inc_pass,
    COUNTIF(ever_inc = 1 AND (cur_state IS NULL OR cur_state NOT IN (7, 39))) inc_left,
    COUNTIF(inc_to_20 = 1) inc_to_20,
    COUNTIF(ever_rev = 1) rev_pass,
    COUNTIF(ever_rev = 1 AND (cur_state IS NULL OR cur_state != 3)) rev_left,
    COUNTIF(rev_to_20 = 1) rev_to_20,
    COUNTIF(ever_inc = 1 AND cur_state IN (7, 39) AND no_tip = 1) inc_reman_notip,
    COUNTIF(ever_rev = 1 AND cur_state = 3 AND no_tip = 1) rev_reman_notip
  FROM enriched WHERE DATE_TRUNC(fecha, MONTH) IN (SELECT p FROM month_periods) GROUP BY c, f, p
),
agg_quarterly AS (
  SELECT 'Q' g, c, fuente_id f, ANY_VALUE(fuente) fn,
    CONCAT(CAST(EXTRACT(YEAR FROM fecha) AS STRING), '-Q', CAST(EXTRACT(QUARTER FROM fecha) AS STRING)) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(ever_inc = 1) inc_pass,
    COUNTIF(ever_inc = 1 AND (cur_state IS NULL OR cur_state NOT IN (7, 39))) inc_left,
    COUNTIF(inc_to_20 = 1) inc_to_20,
    COUNTIF(ever_rev = 1) rev_pass,
    COUNTIF(ever_rev = 1 AND (cur_state IS NULL OR cur_state != 3)) rev_left,
    COUNTIF(rev_to_20 = 1) rev_to_20,
    COUNTIF(ever_inc = 1 AND cur_state IN (7, 39) AND no_tip = 1) inc_reman_notip,
    COUNTIF(ever_rev = 1 AND cur_state = 3 AND no_tip = 1) rev_reman_notip
  FROM enriched WHERE DATE_TRUNC(fecha, QUARTER) IN (SELECT p FROM quarter_periods) GROUP BY c, f, p
),
agg_yearly AS (
  SELECT 'Y' g, c, fuente_id f, ANY_VALUE(fuente) fn, CAST(EXTRACT(YEAR FROM fecha) AS STRING) p,
    COUNT(*) tr, COUNT(DISTINCT nid) t,
    COUNTIF(ever_inc = 1) inc_pass,
    COUNTIF(ever_inc = 1 AND (cur_state IS NULL OR cur_state NOT IN (7, 39))) inc_left,
    COUNTIF(inc_to_20 = 1) inc_to_20,
    COUNTIF(ever_rev = 1) rev_pass,
    COUNTIF(ever_rev = 1 AND (cur_state IS NULL OR cur_state != 3)) rev_left,
    COUNTIF(rev_to_20 = 1) rev_to_20,
    COUNTIF(ever_inc = 1 AND cur_state IN (7, 39) AND no_tip = 1) inc_reman_notip,
    COUNTIF(ever_rev = 1 AND cur_state = 3 AND no_tip = 1) rev_reman_notip
  FROM enriched GROUP BY c, f, p
),

-- Bolsa de leads a gestionar (g='B'): snapshot del stock ACTUAL en estado transitorio
-- SIN tipificar, distribuido por antigüedad (bucket de 5 días desde fecha_creacion).
-- p = inicio del bucket (0,5,10,...). El conteo va en inc_reman_notip (estado 7/39)
-- o rev_reman_notip (estado 3); el frontend acumula ascendente por bucket.
agg_bag AS (
  SELECT 'B' g, c, fuente_id f, ANY_VALUE(fuente) fn,
    CAST(DATE_DIFF(CURRENT_DATE(), fecha, DAY) AS STRING) p,
    0 tr, 0 t, 0 inc_pass, 0 inc_left, 0 inc_to_20, 0 rev_pass, 0 rev_left, 0 rev_to_20,
    COUNTIF(ever_inc = 1 AND cur_state IN (7, 39)) inc_reman_notip,
    COUNTIF(ever_rev = 1 AND cur_state = 3) rev_reman_notip
  FROM enriched
  WHERE no_tip = 1 AND cur_state IN (3, 7, 39)
    AND DATE_DIFF(CURRENT_DATE(), fecha, DAY) BETWEEN 0 AND 365
  GROUP BY c, f, p
),

-- Distribución de duración (g='DUR'): tiempo que cada lead pasó en el estado transitorio
-- (de la PRIMERA entrada al estado a la PRIMERA salida), SOLO leads que lograron salir.
-- p = bucket de 4h (0,4,8,...), tope 2160h (90d) como overflow. Conteo en inc/rev_reman_notip.
flagged AS (
  SELECT c, biz_id, st, ts,
    MIN(IF(st = 3, ts, NULL)) OVER (PARTITION BY c, biz_id) AS first_rev,
    MIN(IF(st IN (7, 39), ts, NULL)) OVER (PARTITION BY c, biz_id) AS first_inc
  FROM ev
),
exit_calc AS (
  SELECT c, biz_id, ANY_VALUE(first_rev) first_rev, ANY_VALUE(first_inc) first_inc,
    MIN(IF(st != 3 AND ts > first_rev, ts, NULL)) AS exit_rev,
    MIN(IF(st NOT IN (7, 39) AND ts > first_inc, ts, NULL)) AS exit_inc
  FROM flagged GROUP BY c, biz_id
),
dur AS (
  SELECT c, biz_id, 'rev' grp, DATETIME_DIFF(exit_rev, first_rev, MINUTE) / 60.0 hours, exit_rev AS exit_ts
  FROM exit_calc WHERE first_rev IS NOT NULL AND exit_rev IS NOT NULL
  UNION ALL
  SELECT c, biz_id, 'inc', DATETIME_DIFF(exit_inc, first_inc, MINUTE) / 60.0, exit_inc
  FROM exit_calc WHERE first_inc IS NOT NULL AND exit_inc IS NOT NULL
),
-- p = "<tier_cohorte>:<bucket_4h>". tier = cohorte por antigüedad de creación
-- (30/45/90/180/365 días) para poder filtrar "creados en los últimos N días" en el front.
agg_dur AS (
  SELECT 'DUR' g, b.c, b.fuente_id f, ANY_VALUE(b.fuente) fn,
    CONCAT(
      CAST(CASE
        WHEN DATE_DIFF(CURRENT_DATE(), b.fecha, DAY) <= 30 THEN 30
        WHEN DATE_DIFF(CURRENT_DATE(), b.fecha, DAY) <= 45 THEN 45
        WHEN DATE_DIFF(CURRENT_DATE(), b.fecha, DAY) <= 90 THEN 90
        WHEN DATE_DIFF(CURRENT_DATE(), b.fecha, DAY) <= 180 THEN 180
        ELSE 365 END AS STRING),
      ':',
      CAST(LEAST(CAST(FLOOR(d.hours / 4) * 4 AS INT64), 2160) AS STRING)
    ) p,
    0 tr, 0 t, 0 inc_pass, 0 inc_left, 0 inc_to_20, 0 rev_pass, 0 rev_left, 0 rev_to_20,
    COUNTIF(d.grp = 'inc') inc_reman_notip,
    COUNTIF(d.grp = 'rev') rev_reman_notip
  FROM dur d
  JOIN base b ON b.c = d.c AND b.biz_id = d.biz_id
  WHERE d.hours >= 0
    AND DATE_DIFF(CURRENT_DATE(), b.fecha, DAY) BETWEEN 0 AND 365
    -- Solo leads que quedaron ATRAPADOS: seguían en el estado >1h tras su creación
    -- (excluye el barrido automático del backbone que entra y sale al instante).
    AND d.exit_ts > DATETIME_ADD(b.fecha_ts, INTERVAL 1 HOUR)
  GROUP BY b.c, b.fuente_id, p
)

SELECT g, c, f, fn, p, tr, t, inc_pass, inc_left, inc_to_20, rev_pass, rev_left, rev_to_20, inc_reman_notip, rev_reman_notip FROM (
  SELECT * FROM agg_daily
  UNION ALL SELECT * FROM agg_weekly
  UNION ALL SELECT * FROM agg_commercial
  UNION ALL SELECT * FROM agg_monthly
  UNION ALL SELECT * FROM agg_quarterly
  UNION ALL SELECT * FROM agg_yearly
  UNION ALL SELECT * FROM agg_bag
  UNION ALL SELECT * FROM agg_dur
)
ORDER BY g, c, f, p
