-- Polígonos de zonas mediana de compra de Habi (CO) + flag abierta/cerrada.
-- Geometría: poligonos_colombia (unique_id = '{zona_mediana_id}-N'), ensamblada y
-- simplificada en BQ (ST_SIMPLIFY 40 m) para que el GeoJSON pese poco.
-- Estado: tabla_validar_zona_mediana.activo (1=abierta), deduplicado por zona (última fecha).
-- Nombre: tabla_inmuebles_general.zona_mediana.
WITH val AS (
  SELECT zona_mediana_id, activo FROM (
    SELECT zona_mediana_id, activo,
           ROW_NUMBER() OVER (PARTITION BY zona_mediana_id ORDER BY fecha_actualizacion DESC) rn
    FROM `papyrus-data.habi_db.tabla_validar_zona_mediana`
  ) WHERE rn = 1
),
nombre AS (
  SELECT zona_mediana_id, ANY_VALUE(zona_mediana) zona
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general`
  WHERE zona_mediana_id IS NOT NULL GROUP BY zona_mediana_id
),
ring AS (
  SELECT CAST(SPLIT(unique_id, '-')[OFFSET(0)] AS INT64) AS zid, unique_id,
         ARRAY_AGG(ST_GEOGPOINT(longitud, latitud) ORDER BY point_index) AS ptarr,
         COUNT(*) npts
  FROM `papyrus-data.habi_wh_bi.poligonos_colombia`
  WHERE unique_id NOT LIKE '0-%'
  GROUP BY zid, unique_id
  HAVING npts >= 4
)
SELECT r.zid,
       n.zona,
       COALESCE(v.activo, 0) AS activo,
       r.npts,
       ST_ASGEOJSON(ST_SIMPLIFY(ST_MAKEPOLYGON(ST_MAKELINE(r.ptarr)), 40)) AS geojson
FROM ring r
LEFT JOIN val v ON v.zona_mediana_id = r.zid
LEFT JOIN nombre n ON n.zona_mediana_id = r.zid
