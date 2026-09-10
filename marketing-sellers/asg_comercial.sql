-- Hoja "Asignado a comercial" · llegada de la cohorte de marketing al comercial (CO y MX)
--
-- La pregunta: de los leads que marketing asignó en un período, ¿cuántos terminaron en
-- manos de un comercial humano, y qué pasa con los que no? Nace del documento
-- `asignados-comercial-mm`, que mostró que una parte de la cohorte se queda en la cola de
-- GABI sin llegar nunca al equipo comercial.
--
-- COHORTE: el indicador de asignados de marketing del WBR
--   (`sellers_leads_asignados_marketing_wbr_mart`, con las 6 fuentes de cada país),
--   bucketeado por `dia` — la fecha en que marketing lo asignó. Cada lead cuenta una vez,
--   en el período de su asignación, y su destino se evalúa a hoy.
--
-- ── LOS INDICADORES ─────────────────────────────────────────────────────────────
--   asg        = tamaño de la cohorte (asignados marketing)
--   comercial  = llegó a un comercial: tiene fila con
--                `tipo_asignacion_comercial = 'Primer Asignación comercial'`
--   sin_com    = NO llegó. Con `comercial` es MECE: suman la cohorte.
--   gabi       = pasó por GABI en algún momento (`tipo = 'gabi'`). Es un corte APARTE,
--                no parte de la descomposición: un lead puede pasar por GABI y llegar
--                igual al comercial.
--   dias_p50   = mediana de días entre la asignación de marketing y la primera
--                asignación comercial, sobre los que sí llegaron.
--
-- ── FUENTES POR PAÍS ────────────────────────────────────────────────────────────
--   CO → `sellers-main-prod.bi_co.seguimiento_asignacion_ibuyer_co`
--   MX → `sellers-main-prod.bi_mx.seguimiento_asignacion_ibuyer`
--   Las dos traen `nid`, `fecha_asignacion`, `tipo` (gabi/comercial) y
--   `tipo_asignacion_comercial`, con los mismos valores, así que los cuatro primeros
--   indicadores son comparables entre países.
--
--   ⚠️ MX tiene además `flag_asignacion_comercial` (aplica_asignacion /
--   no_aplica_asignacion) y `equipo_actual`; CO no tiene ninguna de las dos. El
--   documento `asignados-comercial-mm` usa las dos para afinar la definición de
--   "atascado en GABI": sin `equipo_actual` no se puede distinguir un lead que sigue en
--   la cola de uno que cambió de dueño en HubSpot sin generar la fila de asignación
--   comercial (en MX eran 10 de 562). Aquí NO se usan, para que la definición sea la
--   misma en los dos países; el filtro de `no_aplica_asignacion` quitaría 196 nids en MX.
--   Si algún día CO expone `equipo_actual`, vale volver y separar "atascado en GABI" de
--   "sin comercial por otra razón", que es la partición que de verdad diagnostica.
--
-- ⚠️ LA COHORTE RECIENTE MADURA. Un lead asignado ayer todavía puede llegar al comercial
--   hoy, así que los últimos períodos siempre se ven peor de lo que van a terminar. El
--   documento midió la curva: en abr-jun 2026 el 96,3%-98,5% de la cohorte MX ya tenía
--   comercial al día 6, y ahí se aplanaba. Leer los últimos 6 días con esa cautela.
--
-- NOTA DE ESTRUCTURA: UNNEST que mapea cada fecha a sus 6 claves de período, igual que
--   asg_mm/asg_inmo/asg_total. Cortes iguales a `query.sql`:
--   W = ISOWEEK (lun-dom) · C = WEEK(WEDNESDAY) = ciclo comercial (mié-mar).
--
-- Salida larga: {g, c, p, asg, comercial, sin_com, gabi, dias_p50}.

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

  -- Un registro por nid y país con su destino, desde la tabla de seguimiento de cada uno.
  seguimiento AS (
    SELECT
      'Colombia' AS c,
      CAST(nid AS STRING) AS nid,
      MIN(IF(tipo_asignacion_comercial = 'Primer Asignación comercial',
             DATE(fecha_asignacion), NULL)) AS f_comercial,
      LOGICAL_OR(LOWER(TRIM(tipo)) = 'gabi') AS paso_gabi
    FROM `sellers-main-prod.bi_co.seguimiento_asignacion_ibuyer_co`
    WHERE nid IS NOT NULL
    GROUP BY c, nid

    UNION ALL

    SELECT
      'México',
      CAST(nid AS STRING),
      MIN(IF(tipo_asignacion_comercial = 'Primer Asignación comercial',
             DATE(fecha_asignacion), NULL)),
      LOGICAL_OR(LOWER(TRIM(tipo)) = 'gabi')
    FROM `sellers-main-prod.bi_mx.seguimiento_asignacion_ibuyer`
    WHERE nid IS NOT NULL
    GROUP BY 1, 2
  ),

  base AS (
    SELECT
      co.c,
      co.nid,
      co.fecha,
      s.f_comercial IS NOT NULL                       AS llego_comercial,
      COALESCE(s.paso_gabi, FALSE)                    AS paso_gabi,
      -- Días hasta el comercial. Puede ser negativo si el seguimiento registró la
      -- asignación comercial antes que el mart la fecha de marketing; se descarta.
      IF(s.f_comercial IS NOT NULL AND s.f_comercial >= co.fecha,
         DATE_DIFF(s.f_comercial, co.fecha, DAY), NULL) AS dias
    FROM cohorte co
    LEFT JOIN seguimiento s ON s.c = co.c AND s.nid = co.nid
  ),

  expandido AS (
    SELECT b.c, b.nid, b.llego_comercial, b.paso_gabi, b.dias, gp.g, gp.p
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
  COUNT(DISTINCT e.nid)                                             AS asg,
  COUNT(DISTINCT IF(e.llego_comercial, e.nid, NULL))                AS comercial,
  COUNT(DISTINCT IF(NOT e.llego_comercial, e.nid, NULL))            AS sin_com,
  COUNT(DISTINCT IF(e.paso_gabi, e.nid, NULL))                      AS gabi,
  APPROX_QUANTILES(e.dias, 2)[OFFSET(1)]                            AS dias_p50
FROM expandido e
JOIN vivos v ON v.c = e.c AND v.g = e.g AND v.p = e.p
GROUP BY e.g, e.c, e.p
ORDER BY e.g, e.c, e.p
