-- Mapa de leads por zona (H3) — CO + MX
-- Universo: REGISTROS ABSOLUTOS = nids ÚNICOS de tabla_inmuebles_general (sin filtro marketing),
-- cohorte por fecha de creación, deduplicados por nid (TIG tiene ~2% de nids repetidos;
-- al deduplicar se prefiere la fila CON coordenadas si el nid tiene ambas).
-- Etapas:
--   Registrado = todo nid único registrado.
--   Calificado = fecha_primer_calificacion NOT NULL (flag de TIG, presente en ambos países).
--   Asignado   = nid PRESENTE en el mart de asignados del WBR (universo oficial marketing, 16 filtros).
-- Emite dos tipos de fila (col `kind`):
--   'geo'   = agregado por (pais, mes, fuente, lat/lng ~11 m) → se pinta en el mapa.
--   'nogeo' = agregado por (pais, mes, fuente) sin coordenadas → alimenta el indicador de cobertura.
-- El binning a H3 (res 8/9/10) lo hace el navegador con h3-js sobre las filas 'geo'.
WITH mart AS (
  SELECT DISTINCT nid, pais
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
),
nids AS (
  SELECT 'CO' AS pais, DATE(t.fecha_creacion) AS fc, t.fuente,
         t.latitud AS lat, t.longitud AS lng,
         IF(t.fecha_primer_calificacion IS NOT NULL, 1, 0) AS calif,
         IF(m.nid IS NOT NULL, 1, 0) AS asig,
         IF(t.fecha_cierre IS NOT NULL, 1, 0) AS cierre,
         IF(t.latitud IS NOT NULL AND t.longitud IS NOT NULL AND ABS(t.latitud) > 0 AND ABS(t.longitud) > 0, 1, 0) AS has_geo
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` t
  LEFT JOIN mart m ON m.nid = t.nid AND m.pais = 'colombia'
  WHERE DATE(t.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY t.nid
    ORDER BY IF(t.latitud IS NOT NULL AND ABS(t.latitud) > 0, 1, 0) DESC, t.fecha_creacion
  ) = 1

  UNION ALL

  SELECT 'MX' AS pais, DATE(t.fecha_creacion) AS fc, t.fuente,
         t.latitud AS lat, t.longitud AS lng,
         IF(t.fecha_primer_calificacion IS NOT NULL, 1, 0) AS calif,
         IF(m.nid IS NOT NULL, 1, 0) AS asig,
         IF(t.fecha_cierre IS NOT NULL, 1, 0) AS cierre,
         IF(t.latitud IS NOT NULL AND t.longitud IS NOT NULL AND ABS(t.latitud) > 0 AND ABS(t.longitud) > 0, 1, 0) AS has_geo
  FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` t
  LEFT JOIN mart m ON m.nid = t.nid AND m.pais = 'mexico'
  WHERE DATE(t.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY t.nid
    ORDER BY IF(t.latitud IS NOT NULL AND ABS(t.latitud) > 0, 1, 0) DESC, t.fecha_creacion
  ) = 1
)
SELECT 'geo' AS kind, pais, FORMAT_DATE('%Y-%m', fc) AS mes, fuente,
       ROUND(lat, 4) AS lat, ROUND(lng, 4) AS lng,
       COUNT(*) AS reg, SUM(calif) AS calif, SUM(asig) AS asig, SUM(cierre) AS cierre
FROM nids WHERE has_geo = 1
GROUP BY pais, mes, fuente, lat, lng

UNION ALL

SELECT 'nogeo' AS kind, pais, FORMAT_DATE('%Y-%m', fc) AS mes, fuente,
       NULL AS lat, NULL AS lng,
       COUNT(*) AS reg, SUM(calif) AS calif, SUM(asig) AS asig, SUM(cierre) AS cierre
FROM nids WHERE has_geo = 0
GROUP BY pais, mes, fuente
ORDER BY kind, pais, mes
