-- Hoja "Asignación de leads" · ASIGNADOS INMOBILIARIA (Colombia y México)
--
-- Sirve a dos tablas: la cifra OFICIAL del WBR y su descomposición por historia previa
-- en Market Maker. Tres filas, las dos últimas MECE: suman exactamente el total.
--
-- ⚠️ LOS DOS PAÍSES NO COMPARTEN DEFINICIÓN. No es un espejo como las otras dos queries:
--    cada WBR mide esto con su propia tabla y sus propios filtros, y no hay una fuente
--    común. Lo que sí es igual es la descomposición: en los dos casos la ruta MM→INMO se
--    resuelve contra `hubspot.historical`.
--
-- ── COLOMBIA ────────────────────────────────────────────────────────────────────
--   `sellers-main-prod.bi_co.tablero_asignacion_inmo_col`, por `fecha_primera_asignacion`,
--   con DOS filtros que son parte de la definición:
--     1. `asignacion_consistente = TRUE` — el grueso, quita ~10%. Significa que el lead
--        fue priorizado y asignado el mismo día: en las filas consistentes
--        `dias_asignacion_vs_prioridad` va de −1 a 1 y `mismo_mes_inmo` es TRUE en el 100%.
--        Las inconsistentes son 693 sin prioridad ni fecha de prioridad, más otras
--        asignadas hasta 161 días después de haberse priorizado.
--     2. `prioridad_de_gestion_inmo IN ('A','B')` — el remate: quita solo los
--        'Descartado Gabi', 1-2 por semana.
--   Validado EXACTO en 6 de 6 semanas (2026-09-10): 896 · 1.005 · 1.083 · 974 · 813 · 793.
--   Y al mes: may 4.991 · jul 4.629 · ago 4.032, los tres idénticos al WBR.
--
-- ── MÉXICO ──────────────────────────────────────────────────────────────────────
--   `sellers-main-prod.data_sellers_bo.leads_asignados_imobiliaria` (ojo: "imobiliaria",
--   con una sola m), por `fecha_asignacion`. Es la fuente del indicador "Leads Asignados
--   inmobiliaria" del WBR MX, replicada y anotada en su día en
--   `asignacion-inmo-mx/query_wbr_oficial.sql`.
--   ⚠ NO es HubSpot: la etapa 942483319 del pipeline Inmobiliaria MX se desvía entre −62 y
--     +17 leads por semana, y la entrada al pipeline sobreestima ~10%.
--   ⚠ Esta tabla NO tiene `asignacion_consistente` ni `prioridad_de_gestion_inmo` (la
--     prioridad vive en `hubspot.deals` y es SNAPSHOT), así que los dos filtros de CO no
--     tienen equivalente y no se aplican. El total de MX es todas sus asignaciones.
--   ⚠ `COUNT(*)` cuenta FILAS, no leads: la tabla tiene 202.222 filas para 153.943 nids por
--     reasignaciones. El WBR usa COUNT(*) y por eso su abril-2026 está inflado en 159.
--     Aquí se usa COUNT(DISTINCT nid).
--   ⚠ SIN VALIDAR contra un pantallazo del WBR MX. La serie de CO se verificó semana a
--     semana y ahí apareció un filtro que faltaba; MX no ha pasado por esa prueba. Tratar
--     su nivel absoluto como provisional hasta compararlo con el tablero real.
--
-- ── RUTA MM → INMO (las dos filas de descomposición) ────────────────────────────
--   `sellers-main-prod.hubspot.historical` con propiedad='pipeline' y el pipeline MM del
--   país: MM CO = 798578615 · MM MX = 731899270. MIN(fecha) = primera entrada a MM.
--   ⚠ NO usar `bi_co.seguimiento_asignacion_ibuyer_co.pipeline`: es snapshot del pipeline
--     actual, da 0 casos de "MM primero".
--   ⚠ `historical` tiene ~5 h de rezago: el período en curso va corto.
--
--   `directo` = sin entrada a MM ANTERIOR a su asignación a Inmo (incluye a los que
--   entraron a MM después). Con `de_mm` es MECE.
--   En CO reproduce la línea punteada del WBR "Asignado directo a Inmo (sin pasar por MM)":
--     WBR 481 · 529 · 530 · 485 · 458   |   query 482 · 525 · 528 · 482 · 455
--   ⚠ En MX esa misma etiqueta del WBR mide OTRA COSA ("calificado para real_estate", que
--     no excluye haber pasado por MM), así que la fila de aquí y la línea del WBR MX no
--     son comparables aunque se llamen parecido.
--
-- NOTA DE ESTRUCTURA: UNNEST que mapea cada fecha a sus 6 claves de período, en vez de 6
--   CTEs por país. Cortes iguales a `query.sql`:
--   W = ISOWEEK (lun-dom) · C = WEEK(WEDNESDAY) = ciclo comercial (mié-mar).
--
-- Salida larga: {g, c, p, asg, directo, de_mm}.

WITH
  inmo AS (
    SELECT 'Colombia' AS c, CAST(nid AS STRING) AS nid, fecha_primera_asignacion AS fecha
    FROM `sellers-main-prod.bi_co.tablero_asignacion_inmo_col`
    WHERE asignacion_consistente
      AND prioridad_de_gestion_inmo IN ('A', 'B')
      AND fecha_primera_asignacion IS NOT NULL
      AND nid IS NOT NULL
    UNION ALL
    -- MX: una fila por asignación, así que se colapsa a la primera de cada nid.
    SELECT 'México', CAST(nid AS STRING), MIN(fecha_asignacion)
    FROM `sellers-main-prod.data_sellers_bo.leads_asignados_imobiliaria`
    WHERE fecha_asignacion IS NOT NULL
      AND nid IS NOT NULL
    GROUP BY 1, 2
  ),

  mm AS (
    SELECT
      IF(valor = '798578615', 'Colombia', 'México') AS c,
      CAST(nid AS STRING)                           AS nid,
      MIN(fecha)                                    AS primera_mm
    FROM `sellers-main-prod.hubspot.historical`
    WHERE propiedad = 'pipeline'
      AND valor IN ('798578615', '731899270')
      AND nid IS NOT NULL
    GROUP BY c, nid
  ),

  base AS (
    SELECT
      i.c, i.nid, i.fecha,
      (m.primera_mm IS NOT NULL AND DATE(m.primera_mm) <= i.fecha) AS venia_mm
    FROM inmo i
    LEFT JOIN mm m ON m.c = i.c AND m.nid = i.nid
  ),

  expandido AS (
    SELECT b.c, b.nid, b.venia_mm, gp.g, gp.p
    FROM base b,
    UNNEST([
      STRUCT('D' AS g, CAST(b.fecha AS STRING) AS p),
      ('W', CAST(DATE_TRUNC(b.fecha, ISOWEEK) AS STRING)),
      ('C', CAST(DATE_TRUNC(b.fecha, WEEK(WEDNESDAY)) AS STRING)),
      ('M', FORMAT_DATE('%Y-%m', b.fecha)),
      ('Q', CONCAT(CAST(EXTRACT(YEAR FROM b.fecha) AS STRING), '-Q',
                   CAST(EXTRACT(QUARTER FROM b.fecha) AS STRING))),
      ('Y', CAST(EXTRACT(YEAR FROM b.fecha) AS STRING))
    ]) AS gp
  ),

  vivos AS (
    SELECT c, g, p FROM (
      SELECT c, g, p, ROW_NUMBER() OVER (PARTITION BY c, g ORDER BY p DESC) AS rn
      FROM (SELECT DISTINCT c, g, p FROM expandido)
    ) WHERE rn <= 25
  )

SELECT
  e.g, e.c, e.p,
  COUNT(DISTINCT e.nid)                                    AS asg,
  COUNT(DISTINCT IF(NOT e.venia_mm, e.nid, NULL))          AS directo,
  COUNT(DISTINCT IF(e.venia_mm, e.nid, NULL))              AS de_mm
FROM expandido e
JOIN vivos v ON v.c = e.c AND v.g = e.g AND v.p = e.p
GROUP BY e.g, e.c, e.p
ORDER BY e.g, e.c, e.p
