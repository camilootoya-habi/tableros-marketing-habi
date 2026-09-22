-- Cierres de los deals creados por VENTANAS (Colombia). Los deals se identifican por
-- `primer_agente` en la tabla de inmuebles del backbone: es el `agente` que manda
-- ventanas/leads.py en el POST (VENTANAS_AGENTE_CO), la única marca del programa que
-- llega a BigQuery (utm_campaign viaja vacía por decisión del 21-ago).
-- REGLA DE ORO 4 / METRICAS.md §1: el cierre son DOS líneas de negocio y NO son el mismo
-- evento. Compra directa = Habi compró. Inmobiliaria = el dueño firmó mandato con la red
-- (captación, no venta). Se cuentan las dos, y al presentarlas se dice la composición.
WITH v AS (
  SELECT CAST(negocio_id AS STRING) AS deal_id, nid
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general`
  WHERE primer_agente = 'marketing_loop_ventanas' AND nid IS NOT NULL
),
d AS (
  SELECT nid,
         IF(oportunidad_del_negocio = 'Cierre - Comprado', CAST(closedate AS DATE), NULL) AS f_mm,
         CAST(COALESCE(fecha_captacion_inmobiliaria, fecha_de_contrato_firmado_mx) AS DATE) AS f_inmo,
         CAST(fecha_de_visita AS DATE) AS f_cita
  FROM `sellers-main-prod.hubspot.deals`
  WHERE country = 'Colombia'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC) = 1
)
SELECT v.deal_id, v.nid, d.f_mm, d.f_inmo, d.f_cita
FROM v JOIN d ON d.nid = v.nid
WHERE d.f_mm IS NOT NULL OR d.f_inmo IS NOT NULL OR d.f_cita IS NOT NULL
ORDER BY COALESCE(d.f_mm, d.f_inmo, d.f_cita)
