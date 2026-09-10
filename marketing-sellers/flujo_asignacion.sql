-- Diagrama de flujo de asignación — últimos 14 días de creación (CO + MX)
-- Output largo: g, c, f, node, n   ·   g='D14' (ventana fija, no depende de la granularidad)
--
-- El árbol es MECE en cada nivel: las ramas de un nodo suman exactamente el nodo padre.
-- Las únicas filas que NO particionan van marcadas con el prefijo `x_` (overlays).
--
--   reg ─┬─ no_cal
--        └─ cal ─┬─ cal_sin_owner
--                └─ asignado ─┬─ dest_gabi ─┬─ (equipo) gabi_ibuyer | gabi_inmo
--                             │             └─ (avance) gabi_a_humano | gabi_atascado
--                             ├─ dest_mm        (primer evento es comercial MM)
--                             ├─ dest_inmo      (primer evento es comercial Inmo)
--                             └─ dest_sin_evento (tiene owner pero ningún evento de asignación)
--   overlay: x_gabi_cambio = pasó por los DOS equipos de Gabi (huella del recepcionista)
--
-- Primer destino: se resuelve por TIMESTAMP entre las tres señales. Empate → GABI antes que
-- MM antes que INMO, porque GABI es upstream por diseño. Mismo criterio que asignacion-co.
-- Calificado = el backbone dijo que sí en CUALQUIERA de los dos productos (MM 20/63 o Inmo 20).
-- Asignado = tiene hubspot_owner_id. Es la señal más amplia: la tabla de seguimiento es un
-- subconjunto estricto (nunca hay evento de asignación sin owner).
--
-- ⚠️ La rama gabi_a_humano MADURA: a 14 días va ~73% y a 28 días ~93%. Leer como parcial.

WITH
-- === fuente_detallada: separa WEB/Habímetro en Paid vs Non-Paid y aísla Marketing Loop ===
-- Espejo de ~/habi/queries/asignados_fuentes_paid_{co,mx}.sql, aplicado al universo de REGISTROS.
-- Paid sale del diccionario UTM (Google Sheet): tabla_inmuebles_general.campana_mercadeo unido a
-- registro_unico_utm_mkt_*.campana_mercadeo_original. Se miran los DOS campos a propósito:
-- `mkt_media='Paid'` capta 'WEB Triada' y 'Brand' (pagos con otro nombre de canal), y el LIKE capta
-- las campañas de 'WEB Paid' que quedaron con mkt_media='Otro'.
-- El diccionario trae campañas repetidas → QUALIFY para deduplicar; sin eso el join multiplica filas.
-- Marketing Loop NO es una fuente en TIG: son leads recreados que entran como WEB (y algunos como
-- Leadform/Habímetro). La única marca es la utm_campaign de HubSpot y GANA sobre la fuente original,
-- porque es re-gestión y no lead nuevo.
-- Diferencias vs la query de asignados: acá SÍ existe `propiedades` (46, solo MX), y `crm` trae solo
-- el 20 porque el tablero siempre excluye Ventana (fuente_id=1).
utm_co AS (
  SELECT campana_mercadeo_original, mkt_channel_medium, mkt_media
  FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY campana_mercadeo_original ORDER BY campana_mercadeo_original) = 1
),
utm_mx AS (
  SELECT campana_mercadeo_original, mkt_channel_medium, mkt_media
  FROM `sellers-main-prod.bi_mx.registro_unico_utm_mkt_mexico`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY campana_mercadeo_original ORDER BY campana_mercadeo_original) = 1
),
loop_nids AS (
  SELECT DISTINCT country AS c, nid
  FROM `sellers-main-prod.hubspot.deals`
  WHERE utm_campaign LIKE '%reinteresados%' AND nid IS NOT NULL
),
base AS (
  SELECT 'Colombia' AS c, CAST(tig.nid AS STRING) AS nid, tig.negocio_id AS biz_id,
  CASE
    WHEN lp.nid IS NOT NULL THEN 'loop'
    WHEN tig.fuente_id = 3  THEN IF(COALESCE(u.mkt_media = 'Paid' OR u.mkt_channel_medium LIKE '% Paid', FALSE), 'web_paid', 'web_np')
    WHEN tig.fuente_id = 7  THEN IF(COALESCE(u.mkt_media = 'Paid' OR u.mkt_channel_medium LIKE '% Paid', FALSE), 'habi_paid', 'habi_np')
    WHEN tig.fuente_id = 47 THEN 'leadforms'
    WHEN tig.fuente_id = 20 THEN 'crm'
    WHEN tig.fuente_id = 46 THEN 'propiedades'
    WHEN tig.fuente_id = 39 THEN 'brokers'
    WHEN tig.fuente_id = 35 THEN 'comercial'
    ELSE 'otros'
  END AS fuente_id,
    DATE(tig.fecha_creacion) AS fecha
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN utm_co u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'Colombia'
  WHERE tig.nid IS NOT NULL AND tig.fuente_id IN (3, 7, 20, 35, 39, 47)
    AND DATE(tig.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()

  UNION ALL

  SELECT 'México' AS c, CAST(tig.nid AS STRING), tig.id_negocio,
  CASE
    WHEN lp.nid IS NOT NULL THEN 'loop'
    WHEN tig.fuente_id = 3  THEN IF(COALESCE(u.mkt_media = 'Paid' OR u.mkt_channel_medium LIKE '% Paid', FALSE), 'web_paid', 'web_np')
    WHEN tig.fuente_id = 7  THEN IF(COALESCE(u.mkt_media = 'Paid' OR u.mkt_channel_medium LIKE '% Paid', FALSE), 'habi_paid', 'habi_np')
    WHEN tig.fuente_id = 47 THEN 'leadforms'
    WHEN tig.fuente_id = 20 THEN 'crm'
    WHEN tig.fuente_id = 46 THEN 'propiedades'
    WHEN tig.fuente_id = 39 THEN 'brokers'
    WHEN tig.fuente_id = 35 THEN 'comercial'
    ELSE 'otros'
  END AS fuente_id,
    DATE(tig.fecha_creacion)
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN utm_mx u ON u.campana_mercadeo_original = tig.campana_mercadeo
  LEFT JOIN loop_nids lp ON lp.nid = tig.nid AND lp.c = 'México'
  WHERE tig.nid IS NOT NULL AND tig.fuente_id IN (3, 7, 35, 39, 46, 47)
    AND DATE(tig.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
),

cal AS (
  SELECT 'Colombia' c, negocio_id biz_id FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2` WHERE estado_id IN (20,63) AND negocio_id IS NOT NULL GROUP BY 1,2
  UNION ALL SELECT 'México', deal_id FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state` WHERE state_id IN (20,63) AND deal_id IS NOT NULL GROUP BY 1,2
  UNION ALL SELECT 'Colombia', deal_id FROM `sellers-main-prod.co_rds_staging.habi_db_history_state_real_estate` WHERE state_id=20 AND deal_id IS NOT NULL GROUP BY 1,2
  UNION ALL SELECT 'México', deal_id FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state_real_estate` WHERE state_id=20 AND deal_id IS NOT NULL GROUP BY 1,2
),
cal_u AS (SELECT c, biz_id FROM cal GROUP BY 1,2),

owner AS (
  SELECT CAST(nid AS STRING) nid FROM `sellers-main-prod.hubspot.historical`
  WHERE propiedad='hubspot_owner_id' AND valor IS NOT NULL AND TRIM(valor)<>'' GROUP BY 1
),

ev AS (
  SELECT c, nid,
    MIN(IF(tipo='gabi', ts, NULL))                       AS ts_gabi,
    MIN(IF(tipo='comercial' AND NOT es_inmo, ts, NULL))  AS ts_mm,
    MIN(IF(tipo='comercial' AND es_inmo, ts, NULL))      AS ts_inmo,
    LOGICAL_OR(tipo='comercial')                         AS tuvo_humano,
    LOGICAL_OR(tipo='gabi' AND NOT es_inmo)              AS g_ibuyer,
    LOGICAL_OR(tipo='gabi' AND es_inmo)                  AS g_inmo
  FROM (
    SELECT 'México' c, CAST(nid AS STRING) nid, LOWER(TRIM(tipo)) tipo,
           LOWER(TRIM(IFNULL(equipo_inicial,''))) LIKE '%inmo%' es_inmo, TIMESTAMP(fecha_asignacion) ts
    FROM `sellers-main-prod.bi_mx.seguimiento_asignacion_ibuyer` WHERE fecha_asignacion IS NOT NULL
    UNION ALL
    SELECT 'Colombia', CAST(nid AS STRING), LOWER(TRIM(tipo)),
           LOWER(TRIM(IFNULL(equipo_inicial,''))) LIKE '%inmo%', TIMESTAMP(fecha_asignacion)
    FROM `sellers-main-prod.bi_co.seguimiento_asignacion_ibuyer_co` WHERE fecha_asignacion IS NOT NULL
  )
  GROUP BY 1,2
),

f AS (
  SELECT b.c, b.fuente_id,
    cu.biz_id IS NOT NULL AS es_cal,
    o.nid IS NOT NULL     AS tiene_owner,
    e.nid IS NOT NULL     AS tiene_evento,
    e.ts_gabi, e.ts_mm, e.ts_inmo,
    IFNULL(e.tuvo_humano, FALSE) tuvo_humano,
    IFNULL(e.g_ibuyer, FALSE) g_ibuyer, IFNULL(e.g_inmo, FALSE) g_inmo,
    -- primer destino, por timestamp, empate a favor de GABI
    CASE
      WHEN e.nid IS NULL THEN 'sin_evento'
      WHEN e.ts_gabi IS NOT NULL AND e.ts_gabi <= LEAST(COALESCE(e.ts_mm, TIMESTAMP '9999-12-31'),
                                                        COALESCE(e.ts_inmo, TIMESTAMP '9999-12-31')) THEN 'gabi'
      WHEN e.ts_mm IS NOT NULL AND e.ts_mm <= COALESCE(e.ts_inmo, TIMESTAMP '9999-12-31') THEN 'mm'
      WHEN e.ts_inmo IS NOT NULL THEN 'inmo'
      ELSE 'sin_evento'
    END AS destino
  FROM base b
  LEFT JOIN cal_u cu ON cu.c = b.c AND cu.biz_id = b.biz_id
  LEFT JOIN owner o  ON o.nid = b.nid
  LEFT JOIN ev e     ON e.c = b.c AND e.nid = b.nid
),

nodes AS (
  SELECT c, fuente_id, node, COUNT(*) n FROM f, UNNEST([
    'reg',
    IF(es_cal, 'cal', 'no_cal'),
    IF(es_cal AND NOT tiene_owner, 'cal_sin_owner', NULL),
    IF(es_cal AND tiene_owner, 'asignado', NULL),
    IF(es_cal AND tiene_owner, CONCAT('dest_', destino), NULL),
    IF(es_cal AND tiene_owner AND destino='gabi', IF(g_ibuyer AND NOT g_inmo, 'gabi_solo_ibuyer',
        IF(g_inmo AND NOT g_ibuyer, 'gabi_solo_inmo', 'gabi_ambos')), NULL),
    IF(es_cal AND tiene_owner AND destino='gabi', IF(tuvo_humano, 'gabi_a_humano', 'gabi_atascado'), NULL),
    IF(es_cal AND tiene_owner AND g_ibuyer AND g_inmo, 'x_gabi_cambio', NULL)
  ]) node
  WHERE node IS NOT NULL
  GROUP BY 1,2,3
)
SELECT 'D14' AS g, c, fuente_id AS f, node, n FROM nodes ORDER BY c, f, node
