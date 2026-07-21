-- Completitud de datos de los leads CREADOS (utm reinteresados), por país.
-- 1 fila por lead: fecha_creacion + 1/0 si cada campo del payload quedó POBLADO en el lead creado.
-- "Poblado": strings no vacíos; geo no nula; numéricos > 0. Excluye Web Scraping (fuente_id=4).
-- Lo consume build_data.py (marketing-loop) para armar la tabla de completitud por período/granularidad.
WITH re_mx AS (
  SELECT nid, CAST(CAST(createdate AS DATE) AS STRING) AS fecha
  FROM `sellers-main-prod.hubspot.deals`
  WHERE utm_campaign LIKE '%reinteresados%' AND country='México'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
),
re_co AS (
  SELECT nid, CAST(CAST(createdate AS DATE) AS STRING) AS fecha
  FROM `sellers-main-prod.hubspot.deals`
  WHERE utm_campaign LIKE '%reinteresados%' AND country='Colombia'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC)=1
)
SELECT 'MX' AS pais, re.fecha AS fecha_creacion,
  IF(TRIM(COALESCE(pl.address,''))!='',1,0) AS c_direccion,
  IF(TRIM(COALESCE(g.telefono,''))!='',1,0) AS c_telefono,
  IF(TRIM(COALESCE(g.correo,''))!='',1,0) AS c_email,
  IF(TRIM(COALESCE(g.nombre_inmobiliaria,''))!='',1,0) AS c_nombre,
  IF(g.latitud IS NOT NULL AND g.longitud IS NOT NULL,1,0) AS c_geo,
  IF(COALESCE(pl.median_zone_id,0)>0,1,0) AS c_zona,
  IF(COALESCE(p.property_type_id,0)>0,1,0) AS c_tipo,
  IF(COALESCE(p.area,0)>0,1,0) AS c_area,
  IF(COALESCE(p.bath,0)>0,1,0) AS c_banos,
  IF(p.half_bathroom IS NOT NULL,1,0) AS c_medios_banos,   -- amenidad-conteo: 0 real = "no tiene" (poblado); solo NULL = faltante
  IF(COALESCE(p.room_num,0)>0,1,0) AS c_habitaciones,
  IF(p.garage IS NOT NULL,1,0) AS c_garaje,
  IF(p.elevator IS NOT NULL,1,0) AS c_ascensor,
  IF(COALESCE(p.flat,0)>0,1,0) AS c_piso,
  IF(COALESCE(p.years_old,0)>0,1,0) AS c_antiguedad,
  IF(COALESCE(p.last_ask_price, p.ask_price_real_estate, 0)>0,1,0) AS c_precio,
  CAST(NULL AS INT64) AS c_estrato
FROM re_mx re
JOIN `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` g ON g.nid = re.nid
LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_property` p ON p.id = g.id_inmueble
LEFT JOIN `sellers-main-prod.mx_rds_staging.habi_db_property_location` pl ON pl.id = p.property_location_id
WHERE COALESCE(g.fuente_id,0) <> 4
QUALIFY ROW_NUMBER() OVER (PARTITION BY g.nid ORDER BY CAST(g.fecha_creacion AS DATE) DESC)=1
UNION ALL
SELECT 'CO' AS pais, re.fecha AS fecha_creacion,
  IF(TRIM(COALESCE(loc.direccion_homologada, g.direccion, ''))!='',1,0) AS c_direccion,
  IF(TRIM(COALESCE(g.telefono,''))!='',1,0) AS c_telefono,
  IF(TRIM(COALESCE(g.correo,''))!='',1,0) AS c_email,
  IF(TRIM(COALESCE(g.nombre_o_inmobiliaria,''))!='',1,0) AS c_nombre,
  IF(g.latitud IS NOT NULL AND g.longitud IS NOT NULL,1,0) AS c_geo,
  IF(COALESCE(loc.zona_mediana_id,0)>0,1,0) AS c_zona,
  IF(COALESCE(tiv.tipo_inmueble_id,0)>0,1,0) AS c_tipo,
  IF(COALESCE(tiv.area,0)>0,1,0) AS c_area,
  IF(COALESCE(tiv.banos,0)>0,1,0) AS c_banos,
  CAST(NULL AS INT64) AS c_medios_banos,
  IF(COALESCE(tiv.num_habitaciones,0)>0,1,0) AS c_habitaciones,
  IF(tiv.garajes IS NOT NULL,1,0) AS c_garaje,           -- amenidad-conteo: 0 real = poblado; solo NULL = faltante
  IF(tiv.num_ascensores IS NOT NULL,1,0) AS c_ascensor,
  IF(COALESCE(tiv.num_piso,0)>0,1,0) AS c_piso,
  IF(COALESCE(tiv.anos_antiguedad,0)>0,1,0) AS c_antiguedad,
  IF(COALESCE(tiv.last_ask_price,0)>0,1,0) AS c_precio,
  IF(COALESCE(SAFE_CAST(tiv.estrato AS FLOAT64),0)>0,1,0) AS c_estrato
FROM re_co re
JOIN `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g ON g.nid = re.nid
LEFT JOIN `papyrus-data.habi_db.tabla_inmueble_v2` tiv ON tiv.id = g.inmueble_id
LEFT JOIN `papyrus-data.habi_db.tabla_localizacion_inmueble_v2` loc ON loc.id = tiv.localizacion_new_id
WHERE COALESCE(g.fuente_id,0) <> 4
QUALIFY ROW_NUMBER() OVER (PARTITION BY g.nid ORDER BY CAST(g.fecha_creacion AS DATE) DESC)=1
