-- Negocios creados por VENTANAS (CO) y el día en que se ASIGNARON a comercial.
-- Ventanas no lleva utm_campaign (decisión del 21-ago), así que sus negocios se reconocen por
-- `primer_agente` en el backbone. "Asignado" = aparece en el mart de asignados de marketing de
-- la WBR, la misma fuente que query_asignados.sql usa para el loop web. dia_asignado NULL =
-- se creó pero todavía no pasa los filtros de asignación.
-- El `nid` sirve además para saber qué filas de `recreation` son de Ventanas (por new_nid).
WITH v AS (
  SELECT DISTINCT CAST(nid AS STRING) AS nid
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general`
  WHERE primer_agente = 'marketing_loop_ventanas' AND nid IS NOT NULL
),
m AS (
  SELECT CAST(nid AS STRING) AS nid, MIN(dia) AS dia
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE pais = 'colombia'
  GROUP BY 1
)
SELECT v.nid, CAST(m.dia AS STRING) AS dia_asignado
FROM v LEFT JOIN m USING (nid)
