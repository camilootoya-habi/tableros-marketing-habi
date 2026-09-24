-- marca-mx/queries/exit_poll.sql
-- Exit poll "¿Dónde nos conociste?" MX. Denominador = registros WEB (fuente_id=3):
-- es el único que reproduce la tasa de respuesta de 71-79% del informe original.
SELECT
  FORMAT_DATE('%Y-%m', DATE(fecha_creacion)) AS month,
  CASE
    WHEN estado_mexico IN ('Nuevo Leon', 'Nuevo León') THEN 'MTY'
    WHEN estado_mexico = 'Jalisco'                     THEN 'GDL'
    WHEN estado_mexico IN ('Ciudad de Mexico', 'Ciudad de México',
                           'Distrito Federal', 'Estado de Mexico',
                           'Estado de México', 'Mexico', 'México') THEN 'CDMX'
    ELSE 'Resto'
  END AS plaza,
  donde_nos_conociste AS opcion,
  COUNT(*) AS registros_web
FROM `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general`
WHERE fuente_id = 3
  AND DATE(fecha_creacion) >= '2022-01-01'
  AND DATE(fecha_creacion) < DATE_TRUNC(CURRENT_DATE(), MONTH) + INTERVAL 1 MONTH
GROUP BY 1, 2, 3
