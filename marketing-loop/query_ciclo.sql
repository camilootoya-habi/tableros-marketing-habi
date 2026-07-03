-- Impacto de leads asignados por ciclo/semana — MX + CO — desde la WBR mart.
-- Dos bucketings desde `dia`: tipo='ciclo' (ciclo comercial Miércoles→Martes) y tipo='semana' (Lunes→Domingo).
-- total_asignados = asignados de las 6 fuentes de marketing (se excluye 'Otro'); asignados_reint = subconjunto con UTM reinteresados.
-- Ratio (reint/total) se calcula en el cliente. 1 fila por (tipo, pais, bucket).
WITH reint AS (
  SELECT DISTINCT nid FROM `sellers-main-prod.hubspot.deals`
  WHERE utm_campaign LIKE '%reinteresados%' AND country IN ('México','Colombia')
),
mart AS (
  SELECT DISTINCT nid, pais, dia, fuente_id_tig
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE dia >= DATE_SUB(CURRENT_DATE(), INTERVAL 20 MONTH)   -- suficiente para 20 periodos en cualquier granularidad
    -- 6 fuentes de marketing por país (por fuente_id_tig, igual que los demás tableros):
    -- MX = web(3), estudio inmueble(7), comercial(35), broker(39), propiedades(46), lead forms(47)
    -- CO = web(3), estudio inmueble(7), crm(20), comercial(35), broker(39), leadforms(47)
    AND (
      (pais='mexico'   AND fuente_id_tig IN (3, 7, 35, 39, 46, 47)) OR
      (pais='colombia' AND fuente_id_tig IN (3, 7, 20, 35, 39, 47))
    )
),
joined AS (
  SELECT m.nid, m.pais, m.dia, m.fuente_id_tig, IF(r.nid IS NOT NULL, 1, 0) AS es_reint
  FROM mart m LEFT JOIN reint r ON r.nid = m.nid
)
SELECT 'dia' AS tipo, pais,
  CAST(dia AS STRING) AS bucket,
  COUNT(DISTINCT nid) AS total_asignados,
  COUNT(DISTINCT IF(fuente_id_tig=3, nid, NULL)) AS asignados_web,
  COUNT(DISTINCT IF(es_reint=1, nid, NULL)) AS asignados_reint
FROM joined GROUP BY pais, bucket
UNION ALL
SELECT 'ciclo' AS tipo, pais,
  CAST(DATE_SUB(dia, INTERVAL MOD(EXTRACT(DAYOFWEEK FROM dia) - 4 + 7, 7) DAY) AS STRING) AS bucket,  -- Miércoles
  COUNT(DISTINCT nid) AS total_asignados,
  COUNT(DISTINCT IF(fuente_id_tig=3, nid, NULL)) AS asignados_web,
  COUNT(DISTINCT IF(es_reint=1, nid, NULL)) AS asignados_reint
FROM joined GROUP BY pais, bucket
UNION ALL
SELECT 'semana' AS tipo, pais,
  CAST(DATE_TRUNC(dia, WEEK(MONDAY)) AS STRING) AS bucket,  -- Lunes
  COUNT(DISTINCT nid) AS total_asignados,
  COUNT(DISTINCT IF(fuente_id_tig=3, nid, NULL)) AS asignados_web,
  COUNT(DISTINCT IF(es_reint=1, nid, NULL)) AS asignados_reint
FROM joined GROUP BY pais, bucket
UNION ALL
SELECT 'mes' AS tipo, pais,
  CAST(DATE_TRUNC(dia, MONTH) AS STRING) AS bucket,  -- primer día del mes
  COUNT(DISTINCT nid) AS total_asignados,
  COUNT(DISTINCT IF(fuente_id_tig=3, nid, NULL)) AS asignados_web,
  COUNT(DISTINCT IF(es_reint=1, nid, NULL)) AS asignados_reint
FROM joined GROUP BY pais, bucket
ORDER BY tipo, pais, bucket
