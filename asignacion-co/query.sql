-- Tablero asignación MM vs INMO (CO)
-- Grano de salida: filas largas {kind, lente, d, dim, dim_val, metrica, n}
--   + filas {kind='tiempo', gran, periodo, salto, mediana, p90, n}
-- El frontend bucketea las filas kind='count' a semana/mes/ciclo y toma los últimos 20 períodos.
-- Ventana: 760 días (20 períodos mensuales + colchón de maduración de 90 d).
-- Definiciones: docs/superpowers/specs/2026-08-04-tablero-asignacion-co-design.md

WITH leads AS (
  SELECT
    CAST(t.nid AS STRING)                        AS nid,
    DATE(t.fecha_creacion)                       AS d_creacion,
    t.fuente_id                                  AS fuente_id,
    COALESCE(NULLIF(TRIM(t.fuente), ''), '(sin fuente)')                AS fuente,
    COALESCE(NULLIF(TRIM(t.area_metropolitana), ''), '(sin área)')      AS area
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` t
  WHERE t.nid IS NOT NULL
    AND DATE(t.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 760 DAY)
    AND DATE(t.fecha_creacion) <  CURRENT_DATE()
)
SELECT 'count' AS kind, 'A' AS lente, d_creacion AS d,
       'total' AS dim, 'total' AS dim_val, 'creados' AS metrica,
       COUNT(DISTINCT nid) AS n
FROM leads
GROUP BY d
