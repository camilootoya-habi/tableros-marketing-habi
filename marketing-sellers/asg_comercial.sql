-- Hoja "Asignado a comercial" · llegada de la cohorte de marketing al comercial (CO y MX)
--
-- Sigue las definiciones del documento `asignados-comercial-mm`, no una versión propia.
--
-- COHORTE: el indicador de asignados de marketing del WBR
--   (`sellers_leads_asignados_marketing_wbr_mart`, con las 6 fuentes de cada país), por su
--   `dia` de asignación. Cada lead cuenta una vez y su destino se evalúa a hoy.
--
-- ── LAS CINCO FILAS, MECE: suman exactamente la cohorte ──────────────────────────
--   comercial   = llegó a un comercial REAL
--   descartador = su única asignación comercial fue al descartador
--   atascado    = las 5 condiciones de "atascado en GABI" del documento
--   transito    = sin comercial, pero todavía dentro de la ventana de 6 días
--   otra        = sin comercial, ya pasaron 6 días, y NO sigue en GABI
--
-- ── "ATASCADO EN GABI": LAS CINCO CONDICIONES DEL DOCUMENTO ──────────────────────
--   1. Está en el indicador de asignados marketing del WBR  → es la cohorte.
--   2. GABI lo recibió                                      → `tipo = 'gabi'`.
--   3. NO tiene 'Primer Asignación comercial'.
--      En MX el documento exige además `flag_asignacion_comercial='aplica_asignacion'`;
--      CO no tiene esa columna (ver abajo).
--   4. Pasaron 6 días o más desde la asignación de marketing.
--      Por qué 6: en abr-jun 2026 el 96,3%-98,5% de la cohorte ya tenía comercial al día 6
--      y la curva se aplanaba ahí. Un lead que pasa el día 6 sin comercial históricamente
--      ya no salía. Antes del día 6 no está atascado: está EN TRÁNSITO, y por eso es una
--      fila aparte y no se mezcla con la fuga.
--   5. SIGUE EN MANOS DE GABI HOY. Es la condición que el documento marca como la
--      importante: sin ella el query devolvía 562 leads, pero 10 ya estaban con un
--      comercial real —cambiaron de propietario en HubSpot sin que se creara la fila de
--      "Primer Asignación comercial"—, así que la condición 3 sola los marcaba atascados
--      cuando no lo estaban.
--      MX → `equipo_actual` empieza por 'gabi' (gabi ibuyer / gabi inmobiliaria).
--      CO → no tiene `equipo_actual`; el equivalente es `propietario_actual = 'iagabi@habi.co'`.
--
--   ⚠️ ASIMETRÍA QUE HAY QUE TENER PRESENTE: MX aplica las 5 condiciones completas. CO
--   aplica 4 y media — le falta `flag_asignacion_comercial` (que en MX excluye 196 nids
--   marcados `no_aplica_asignacion`) y su condición 5 va por `propietario_actual` en vez
--   de `equipo_actual`. Son columnas que CO no expone. El número de CO es por tanto un
--   límite inferior del atascamiento, no una medición idéntica a la de MX.
--
-- ── EL DESCARTADOR ──────────────────────────────────────────────────────────────
--   `susanaescobar@habi.co` no es un comercial: es la cuenta a la que van los leads
--   descartados, en los DOS países (5.469 nids en MX, 1.306 en CO).
--   ⚠ Antes se contaban como "llegaron a comercial", así que la métrica venía inflada, y
--   cada vez más. Medido 2026-09-10 como % de los que figuraban como llegados:
--     CO  1,5% (may) → 3,4% (jul) → 4,3% (ago) → 6,0% (sep)
--     MX  1,3% (may) → 4,8% (jul) → 8,1% (ago) → 13,7% (sep)
--   ⚠ OJO CON EL NOMBRE: hay otras Susanas que SÍ son comerciales
--   (`susanacosme@tuhabi.mx` 2.650 nids, `susanabaez@tuhabi.mx` 1.988). El filtro va por
--   correo exacto, nunca por LIKE '%susana%'.
--   Un lead que pasó por el descartador y DESPUÉS llegó a un comercial real cuenta como
--   `comercial`: importa si terminó gestionado, no por dónde pasó.
--
-- ── OTROS INDICADORES ───────────────────────────────────────────────────────────
--   gabi     = pasó por GABI en algún momento. Corte APARTE, no parte de la partición.
--   dias_p50 = mediana de días hasta la primera asignación a un comercial real.
--
-- FUENTES: `bi_co.seguimiento_asignacion_ibuyer_co` y `bi_mx.seguimiento_asignacion_ibuyer`.
--
-- ⚠️ LA COHORTE RECIENTE MADURA: los últimos 6 días no se leen todavía. Por eso la fila
--   `transito` existe — para que esos leads no se cuenten como fuga.
--
-- Salida larga: {g, c, p, asg, comercial, descartador, atascado, transito, otra,
--                gabi, dias_p50}.

WITH
  cohorte AS (
    SELECT DISTINCT
      IF(pais = 'colombia', 'Colombia', 'México') AS c,
      CAST(nid AS STRING)                         AS nid,
      dia                                         AS fecha
    FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
    WHERE pais IN ('colombia', 'mexico')
      AND (
        (pais = 'colombia' AND fuente_id_tig IN (3, 7, 20, 35, 39, 47, 37, 41, 42))
        OR
        (pais = 'mexico'   AND fuente_id_tig IN (3, 7, 46, 35, 39, 47))
      )
  ),

  seguimiento AS (
    -- COLOMBIA: sin `flag_asignacion_comercial` ni `equipo_actual`.
    SELECT
      'Colombia' AS c,
      CAST(nid AS STRING) AS nid,
      MIN(IF(tipo_asignacion_comercial = 'Primer Asignación comercial'
             AND LOWER(TRIM(IFNULL(hubspot_owner_id, ''))) <> 'susanaescobar@habi.co',
             DATE(fecha_asignacion), NULL))                                    AS f_comercial,
      LOGICAL_OR(tipo_asignacion_comercial = 'Primer Asignación comercial'
                 AND LOWER(TRIM(IFNULL(hubspot_owner_id, ''))) = 'susanaescobar@habi.co')
                                                                               AS toco_descartador,
      LOGICAL_OR(LOWER(TRIM(tipo)) = 'gabi')                                   AS paso_gabi,
      -- condición 5, equivalente de CO
      LOGICAL_OR(LOWER(TRIM(IFNULL(propietario_actual, ''))) = 'iagabi@habi.co') AS sigue_gabi
    FROM `sellers-main-prod.bi_co.seguimiento_asignacion_ibuyer_co`
    WHERE nid IS NOT NULL
    GROUP BY c, nid

    UNION ALL

    -- MÉXICO: con las 5 condiciones completas.
    SELECT
      'México',
      CAST(nid AS STRING),
      MIN(IF(tipo_asignacion_comercial = 'Primer Asignación comercial'
             AND flag_asignacion_comercial = 'aplica_asignacion'
             AND LOWER(TRIM(IFNULL(hubspot_owner_id, ''))) <> 'susanaescobar@habi.co',
             DATE(fecha_asignacion), NULL)),
      LOGICAL_OR(tipo_asignacion_comercial = 'Primer Asignación comercial'
                 AND LOWER(TRIM(IFNULL(hubspot_owner_id, ''))) = 'susanaescobar@habi.co'),
      LOGICAL_OR(LOWER(TRIM(tipo)) = 'gabi'),
      LOGICAL_OR(STARTS_WITH(LOWER(TRIM(IFNULL(equipo_actual, ''))), 'gabi'))
    FROM `sellers-main-prod.bi_mx.seguimiento_asignacion_ibuyer`
    WHERE nid IS NOT NULL
    GROUP BY 1, 2
  ),

  base AS (
    SELECT
      co.c, co.nid, co.fecha,
      s.f_comercial IS NOT NULL                                        AS llego,
      (s.f_comercial IS NULL AND COALESCE(s.toco_descartador, FALSE))  AS descartador,
      COALESCE(s.paso_gabi, FALSE)                                     AS paso_gabi,
      COALESCE(s.sigue_gabi, FALSE)                                    AS sigue_gabi,
      -- condición 4: la ventana de 6 días del documento
      DATE_DIFF(CURRENT_DATE(), co.fecha, DAY) >= 6                    AS vencido,
      IF(s.f_comercial IS NOT NULL AND s.f_comercial >= co.fecha,
         DATE_DIFF(s.f_comercial, co.fecha, DAY), NULL)                AS dias
    FROM cohorte co
    LEFT JOIN seguimiento s ON s.c = co.c AND s.nid = co.nid
  ),

  clasificado AS (
    SELECT
      c, nid, fecha, paso_gabi, dias,
      CASE
        WHEN llego                                              THEN 'comercial'
        WHEN descartador                                        THEN 'descartador'
        WHEN NOT vencido                                        THEN 'transito'
        WHEN paso_gabi AND sigue_gabi                           THEN 'atascado'
        ELSE                                                         'otra'
      END AS destino
    FROM base
  ),

  expandido AS (
    SELECT b.c, b.nid, b.destino, b.paso_gabi, b.dias, gp.g, gp.p
    FROM clasificado b,
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
  COUNT(DISTINCT e.nid)                                              AS asg,
  COUNT(DISTINCT IF(e.destino = 'comercial',   e.nid, NULL))         AS comercial,
  COUNT(DISTINCT IF(e.destino = 'descartador', e.nid, NULL))         AS descartador,
  COUNT(DISTINCT IF(e.destino = 'atascado',    e.nid, NULL))         AS atascado,
  COUNT(DISTINCT IF(e.destino = 'transito',    e.nid, NULL))         AS transito,
  COUNT(DISTINCT IF(e.destino = 'otra',        e.nid, NULL))         AS otra,
  COUNT(DISTINCT IF(e.paso_gabi,               e.nid, NULL))         AS gabi,
  APPROX_QUANTILES(e.dias, 2)[OFFSET(1)]                             AS dias_p50
FROM expandido e
JOIN vivos v ON v.c = e.c AND v.g = e.g AND v.p = e.p
GROUP BY e.g, e.c, e.p
ORDER BY e.g, e.c, e.p
