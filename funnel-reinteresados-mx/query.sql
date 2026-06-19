-- Funnel + antifunnel + evolución diaria de la campaña "reinteresados" (WEB, MX).
-- Universo: utm_campaign de la campaña, fuente WEB (fuente_id=3), MX.
-- Filas (col `kind`):
--   'funnel' = etapas de la progresión (orden en `grupo`): Registros → Calificados (alguna vez 20/63)
--              → Asignados (WBR mart) → Citas agendadas (alguna vez estado 27). `n` = NIDs.
--   'estado' = breakdown por estado ACTUAL; n = total, n_asig = asignados (resto = no asignados).
--              grupo: 20/63 = Calificado · resto = Antifunnel.
--   'diario' = cohorte por fecha de creación; n = registros, n_calif = calificados (estado actual 20/63).
WITH ea AS (
  SELECT deal_id, ARRAY_AGG(state_id ORDER BY date_create DESC, id DESC LIMIT 1)[OFFSET(0)] AS cur
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state` GROUP BY deal_id
),
ever AS (
  SELECT deal_id, MAX(IF(state_id IN (20,63),1,0)) AS ever_calif, MAX(IF(state_id=27,1,0)) AS ever_cita
  FROM `sellers-main-prod.mx_rds_staging.habi_db_history_state` GROUP BY deal_id
),
mart AS (
  SELECT DISTINCT nid FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart` WHERE pais='mexico'
),
base AS (
  SELECT g.nid, ea.cur AS sid, CAST(g.fecha_creacion AS DATE) AS fc,
         COALESCE(ev.ever_calif,0) AS ever_calif, COALESCE(ev.ever_cita,0) AS ever_cita,
         IF(m.nid IS NOT NULL,1,0) AS asignado
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g
  JOIN `sellers-main-prod.hubspot.deals` hd ON hd.nid = g.nid AND hd.country = "México"
  LEFT JOIN ea ON ea.deal_id = g.id_negocio
  LEFT JOIN ever ev ON ev.deal_id = g.id_negocio
  LEFT JOIN mart m ON m.nid = g.nid
  WHERE hd.utm_campaign = "mex-sellers-paid-experiments-web-without-leads-retargeting-national-reinteresados"
    AND g.fuente_id = 3
  QUALIFY ROW_NUMBER() OVER (PARTITION BY g.nid ORDER BY CAST(g.fecha_creacion AS DATE) DESC) = 1
)
SELECT 'funnel' AS kind, CAST(orden AS STRING) AS grupo, CAST(NULL AS STRING) AS state_id,
       label, CAST(NULL AS STRING) AS fecha, n, 0 AS n_asig, 0 AS n_calif
FROM (
  SELECT 1 AS orden, "Registros" AS label, COUNT(*) AS n FROM base
  UNION ALL SELECT 2, "Calificados",      COUNTIF(ever_calif=1) FROM base
  UNION ALL SELECT 3, "Asignados",        COUNTIF(asignado=1)   FROM base
  UNION ALL SELECT 4, "Citas agendadas",  COUNTIF(ever_cita=1)  FROM base
)
UNION ALL
SELECT 'estado', IF(b.sid IN (20,63),"Calificado","Antifunnel"), CAST(b.sid AS STRING),
       COALESCE(st.label,"Sin estado"), CAST(NULL AS STRING), COUNT(*), COUNTIF(b.asignado=1), 0
FROM base b LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_state` st ON st.id = b.sid
GROUP BY 2,3,4
UNION ALL
SELECT 'diario', CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING),
       CAST(fc AS STRING), COUNT(*), 0, COUNTIF(sid IN (20,63))
FROM base GROUP BY fc
ORDER BY kind, grupo, n DESC
