-- Cierres y captaciones POR MES de los leads con UTM del Marketing Loop (CO + MX).
-- Una fila por (mes, país). El mes es el del EVENTO (cierre/captación), no el de creación del lead.
--
-- Cohorte: mismo predicado de UTM que query_asignados.sql. Si se cambia aquí hay que cambiarlo allá,
-- o las dos secciones del tablero dejan de hablar de la misma población.
--
-- Escanea ~9,3 GB y NO baja con filtros de fecha (las tablas no están particionadas por `fecha`).
-- Por eso corre en su propio cron diario (update-loop-cierres.yml), no en el de 10 minutos.
-- El 71% del escaneo es `seguimiento_inmobiliaria_mex_copia` (6,55 GB); las otras tres son 0,08 GB.

WITH loop_nids AS (
  SELECT DISTINCT
    CAST(nid AS STRING)                      AS nid,
    IF(country = 'Colombia', 'CO', 'MX')     AS pais
  FROM `sellers-main-prod.hubspot.deals`
  WHERE utm_campaign LIKE '%reinteresados%'
    AND country IN ('Colombia', 'México')
    AND nid IS NOT NULL
),

eventos AS (
  -- CO captación = la etapa completa. Esta es la ÚNICA de las cuatro tablas donde `etapa` es el
  -- nombre del hito (en las otras el evento vive en `valor`). Bajo esta etapa solo existen dos
  -- valores: 'Captación normal' (11.523 nids, viva) y 'Captación automatica' (1.693, se apagó el
  -- 29-abr-2026). Se toman las dos: filtrar por `valor` aquí solo agregaría una forma de quedarse
  -- corto si mañana aparece un tercer tipo de captación.
  SELECT 'CO' AS pais, 'captaciones' AS metrica, DATE(fecha) AS fecha, CAST(nid AS STRING) AS nid
  FROM `sellers-main-prod.bi_co.seguimiento_inmobiliaria_col`
  WHERE etapa = 'Captaciones'

  UNION ALL
  -- CO cierre = compra cerrada. `Cierre OCD` es el MISMO evento visto dos veces (1.380 nids traen los
  -- dos valores y 1.295 en la misma fecha exacta), así que sumarlo duplicaría el cierre → excluido.
  SELECT 'CO', 'cierres', DATE(fecha), CAST(nid AS STRING)
  FROM `papyrus-data.habi_wh_bi.funnel_diarios_col`
  WHERE TRIM(valor) = 'Cierre - Comprado'

  UNION ALL
  -- MX captación = 'Firma', último hito del funnel INMO. Esta tabla trae ~775 filas por nid
  -- (1.507.492 filas para 1.944 nids), así que el COUNT(DISTINCT) de abajo no es opcional.
  SELECT 'MX', 'captaciones', DATE(fecha), CAST(nid AS STRING)
  FROM `sellers-main-prod.bi_mx.seguimiento_inmobiliaria_mex_copia`
  WHERE valor = 'Firma'

  UNION ALL
  -- MX cierre. Algunos valores traen doble espacio ('Cierre  OCD'), de ahí el REGEXP en vez de TRIM.
  SELECT 'MX', 'cierres', DATE(fecha), CAST(nid AS STRING)
  FROM `sellers-main-prod.bi_mx.seguimiento_funnel_mex`
  WHERE REGEXP_REPLACE(TRIM(valor), r'\s+', ' ') = 'Cierre - Comprado'
),

loop_ev AS (
  SELECT
    e.pais,
    e.metrica,
    FORMAT_DATE('%Y-%m', e.fecha) AS mes,
    e.nid
  FROM eventos AS e
  INNER JOIN loop_nids AS l
    ON l.nid = e.nid AND l.pais = e.pais
)

SELECT
  mes,
  pais,
  COUNT(DISTINCT IF(metrica = 'captaciones', nid, NULL)) AS captaciones,
  COUNT(DISTINCT IF(metrica = 'cierres',     nid, NULL)) AS cierres
FROM loop_ev
GROUP BY mes, pais
ORDER BY mes, pais;
