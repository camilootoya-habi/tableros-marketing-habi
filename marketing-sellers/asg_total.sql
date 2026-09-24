-- Hoja "Asignación de leads" · ASIGNADOS TOTALES y su reparto por producto (CO y MX)
--
-- Universo: todo lead que (a) fue calificado para Market Maker o para Inmobiliaria, y
-- (b) se asignó a un `hubspot_owner_id`. Bucketeado por la fecha de su PRIMERA asignación.
--
-- Cuatro filas, las tres últimas MECE: suman exactamente el total.
--   asg        = asignados totales
--   solo_mm    = calificado para MM y nunca para Inmo
--   solo_inmo  = calificado para Inmo y nunca para MM
--   ambos      = calificado para los dos productos
--
-- ── CALIFICACIÓN: por PASO POR ESTADO, no por `product_qualified` ────────────────
--   Colombia
--     MM   → `estado_id IN (20, 63)` en `co_rds_staging.habi_db_tabla_historico_estado_v2`
--            (por `negocio_id`, que es el `id` de `habi_db_tabla_negocio_inmueble`)
--     INMO → `state_id = 20` en `co_rds_staging.habi_db_history_state_real_estate`
--            (por `deal_id`, el mismo `id`)
--   México
--     MM   → `state_id IN (20, 63)` en `mx_rds_staging.habi_db_history_state`
--     INMO → `state_id = 20` en `mx_rds_staging.habi_db_history_state_real_estate`
--            (los dos por `deal_id`, que es el `id` de `habi_db_property_deal`)
--   Son las mismas fuentes e ids que usa `query.sql` de este tablero para "Calificados MM"
--   y "Calificados Inmo" en cada país, así que las dos hojas hablan el mismo idioma.
--
--   Se prefiere sobre `product_qualified` por tres razones, medidas 2026-09-10 en CO:
--     1. Es un evento ("pasó por"), no el snapshot del último valor.
--     2. Es un SUPERCONJUNTO estricto: la definición ampliada (estados OR
--        product_qualified) da exactamente lo mismo que estados solos en los 16 meses
--        revisados. Todo lead con `product_qualified` pasó por esos estados.
--     3. Recoge algo más: jul 7.104 vs 7.059 · ago 7.558 vs 7.509.
--
-- ── ⚠️ VENTANA POR PAÍS: ES EL LÍMITE DEL DATO, NO UNA DECISIÓN ──────────────────
--   La historia de estados de Inmo no arranca igual en los dos países, y sin ella no
--   existe la mitad "Inmo" de la definición. Un total hacia atrás daría solo la parte de
--   MM, que es otra cosa y se leería como una caída del indicador. Por eso cada país
--   arranca donde su tabla arranca, y los períodos anteriores van en NULL → "—".
--   En CO son 2026-03; el corte de MX lo fija la misma tabla en `mx_rds_staging`.
--   Cambiar de `product_qualified` a estados NO mueve ese límite: en CO
--   `product_qualified` también arranca en marzo-2026 (feb 678 → mar 4.610 de ~15.800
--   asignados/mes). Los dos sistemas empezaron a registrar calificación a la vez.
--
-- ⚠️ NO ES CITABLE en el WBR ni en el OKR: ahí se reporta el mart. Esta tabla dimensiona
--   la operación de asignación completa. Referencia CO (jul-2026): 7.104 contra 5.147.
--
-- SIN FILTRO DE FUENTE, a propósito: en CO, restringir a las 6 fuentes de marketing daba
--   el mismo número, así que se omite el join a `tabla_inmuebles_general` — la tabla más
--   grande — y la query no paga ese escaneo.
--
-- NOTA DE ESTRUCTURA: se usa un UNNEST que mapea cada fecha a sus 6 claves de período en
--   vez de 6 CTEs por país (12 bloques casi idénticos). Cortes iguales a `query.sql`:
--   W = ISOWEEK (lun-dom) · C = WEEK(WEDNESDAY) = ciclo comercial (mié-mar).
--
-- Salida larga: {g, c, p, asg, solo_mm, solo_inmo, ambos}.

WITH
  -- nid ↔ id del negocio, por país
  negocios AS (
    SELECT 'Colombia' AS c, CAST(nid AS STRING) AS nid, id AS biz_id
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble`
    WHERE nid IS NOT NULL
    UNION ALL
    SELECT 'México', CAST(nid AS STRING), id
    FROM `sellers-main-prod.mx_rds_staging.habi_db_property_deal`
    WHERE nid IS NOT NULL
  ),

  cal_mm AS (
    SELECT DISTINCT n.c, n.nid
    FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2` h
    JOIN negocios n ON n.c = 'Colombia' AND n.biz_id = h.negocio_id
    WHERE h.estado_id IN (20, 63)
    UNION DISTINCT
    SELECT DISTINCT n.c, n.nid
    FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state` h
    JOIN negocios n ON n.c = 'México' AND n.biz_id = h.deal_id
    WHERE h.state_id IN (20, 63)
  ),

  cal_inmo AS (
    SELECT DISTINCT n.c, n.nid
    FROM `sellers-main-prod.co_rds_staging.habi_db_history_state_real_estate` h
    JOIN negocios n ON n.c = 'Colombia' AND n.biz_id = h.deal_id
    WHERE h.state_id = 20
    UNION DISTINCT
    SELECT DISTINCT n.c, n.nid
    FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state_real_estate` h
    JOIN negocios n ON n.c = 'México' AND n.biz_id = h.deal_id
    WHERE h.state_id = 20
  ),

  -- Primer día en que el lead tuvo dueño comercial. `historical` no separa por país,
  -- así que el país lo aporta el lado de la calificación.
  owner AS (
    SELECT CAST(nid AS STRING) AS nid, MIN(DATE(fecha)) AS fecha
    FROM `sellers-main-prod.hubspot.historical`
    WHERE propiedad = 'hubspot_owner_id'
      AND valor IS NOT NULL AND TRIM(valor) <> ''
      AND nid IS NOT NULL
    GROUP BY nid
  ),

  -- Desde cuándo hay historia de estados de Inmo en cada país. Es el piso de la serie.
  piso AS (
    SELECT c, MIN(fecha) AS desde FROM (
      SELECT 'Colombia' AS c, MIN(DATE(date_create)) AS fecha
      FROM `sellers-main-prod.co_rds_staging.habi_db_history_state_real_estate`
      WHERE state_id = 20
      UNION ALL
      SELECT 'México', MIN(DATE(date_create))
      FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state_real_estate`
      WHERE state_id = 20
    ) GROUP BY c
  ),

  base AS (
    SELECT
      cal.c,
      cal.nid,
      o.fecha,
      cal.es_mm,
      cal.es_inmo
    FROM (
      SELECT
        COALESCE(mm.c, inmo.c)     AS c,
        COALESCE(mm.nid, inmo.nid) AS nid,
        mm.nid IS NOT NULL         AS es_mm,
        inmo.nid IS NOT NULL       AS es_inmo
      FROM cal_mm mm
      FULL OUTER JOIN cal_inmo inmo ON inmo.c = mm.c AND inmo.nid = mm.nid
    ) cal
    JOIN owner o ON o.nid = cal.nid
    JOIN piso  pi ON pi.c = cal.c
    WHERE o.fecha >= pi.desde
  ),

  expandido AS (
    SELECT b.c, b.nid, b.es_mm, b.es_inmo, gp.g, gp.p
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
  COUNT(DISTINCT e.nid)                                                    AS asg,
  COUNT(DISTINCT IF(e.es_mm AND NOT e.es_inmo, e.nid, NULL))               AS solo_mm,
  COUNT(DISTINCT IF(e.es_inmo AND NOT e.es_mm, e.nid, NULL))               AS solo_inmo,
  COUNT(DISTINCT IF(e.es_mm AND e.es_inmo, e.nid, NULL))                   AS ambos
FROM expandido e
JOIN vivos v ON v.c = e.c AND v.g = e.g AND v.p = e.p
GROUP BY e.g, e.c, e.p
ORDER BY e.g, e.c, e.p
