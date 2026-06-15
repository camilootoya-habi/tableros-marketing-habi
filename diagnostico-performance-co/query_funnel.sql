-- Registros, asignados y CVR(registro->asignado) por fuente de performance CO.
-- Cohort: agrupa por fecha_creacion; asg = el nid llegó EN ALGÚN MOMENTO a Primer_asigancion.
-- Diario; el build agrega a semana ISO. Historia desde 2025-01-01.
WITH funnel_reach AS (
  SELECT nid, MIN(IF(valor='Primer_asigancion', DATE(fecha), NULL)) AS asg_date
  FROM `papyrus-data.habi_wh_bi.funnel_diarios_col`
  WHERE nid IS NOT NULL
  GROUP BY nid
),
base AS (
  SELECT tig.nid, tig.fuente, DATE(tig.fecha_creacion) AS fecha, fr.asg_date
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN funnel_reach fr ON fr.nid = tig.nid
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) >= '2025-01-01'
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente IN ('WEB','lead_forms','Estudio Inmueble')
)
SELECT
  CAST(fecha AS STRING) AS dt,
  fuente,
  COUNT(DISTINCT nid) AS registros,
  COUNT(DISTINCT IF(asg_date IS NOT NULL, nid, NULL)) AS asignados
FROM base
GROUP BY 1, 2
ORDER BY 1, 2
