# Métricas del Marketing Loop — definiciones canónicas

Este archivo existe porque el cierre se contó mal durante meses y el error es fácil de repetir:
la métrica *parece* correcta, la query corre sin fallar, y el número que sale es plausible.

## Cierre: SIEMPRE son DOS líneas de negocio

Habi vende por dos vías y **cada una guarda su cierre en un campo distinto** de
`sellers-main-prod.hubspot.deals`:

| Línea | Campo | Valores que son cierre |
|---|---|---|
| iBuyer / Market Maker | `oportunidad_del_negocio` | `'Cierre - Comprado'` |
| Inmobiliaria | `oportunidad_inmobiliaria` | `'Contrato firmado'`, `'Ya vendio'` |

**Contar solo `oportunidad_del_negocio` subregistra los cierres del loop 2.5x.** Medido el
2026-08-21 sobre la población del loop (`utm_campaign LIKE '%reinteresados%'`, deduplicado por
nid, 4.468 deals):

| País | iBuyer | Inmobiliaria | Unión (correcto) |
|---|---|---|---|
| Colombia | 9 | 29 | **38** |
| México | 10 | 0 | **10** |
| **Total** | **19** | **29** | **48** |

El solapamiento entre las dos líneas es **cero**, así que la unión es la suma. En Colombia el
error es brutal: contando solo iBuyer se reportan 9 de 38 cierres reales. En México no se nota
porque la línea inmobiliaria aún no tiene cierres del loop — eso hace que el bug pase
desapercibido si solo se mira MX.

### La forma correcta

```sql
-- Cierre = cualquiera de las dos líneas. NO uses solo oportunidad_del_negocio.
IF(oportunidad_del_negocio = 'Cierre - Comprado'
   OR oportunidad_inmobiliaria IN ('Contrato firmado','Ya vendio'), 1, 0) AS cierre
```

### Cómo verificar en 30 segundos

Si tocas cualquier query de cierres, corre esto y compara: si tu número se parece a la columna
`ibuyer` en vez de a `union_ambas`, te falta la línea inmobiliaria.

```sql
WITH d AS (
  SELECT nid, country, oportunidad_del_negocio AS op_mm, oportunidad_inmobiliaria AS op_in
  FROM `sellers-main-prod.hubspot.deals`
  WHERE country IN ('México','Colombia') AND utm_campaign LIKE '%reinteresados%'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC) = 1
)
SELECT country,
  COUNTIF(op_mm = 'Cierre - Comprado') AS ibuyer,
  COUNTIF(op_in IN ('Contrato firmado','Ya vendio')) AS inmobiliaria,
  COUNTIF(op_mm = 'Cierre - Comprado'
          OR op_in IN ('Contrato firmado','Ya vendio')) AS union_ambas
FROM d GROUP BY 1 ORDER BY 1
```

## Fecha del cierre: usa `closedate`

`fecha_de_firma` está **vacía en toda la tabla** (0 de 3.287 cierres la traen). `closedate` sí
está poblada: los 19 cierres iBuyer del loop la tienen, ninguno nulo.

- **KPI de cabecera** (MTD/WTD/YTD): filtra por `closedate`.
- **Funnel por cohorte**: NO filtra por fecha de cierre; agrupa por antigüedad de `createdate`
  y cuenta los cierres de esa gente, hayan ocurrido cuando hayan ocurrido. Los dos números son
  distintos **por diseño** y ambos son correctos; no intentes hacerlos coincidir.

## Atribución al loop: `utm_campaign`

Un lead es del Marketing Loop si su `utm_campaign` contiene `reinteresados`
(`col-sellers-paid-experiments-web-without-leads-retargeting-national-reinteresados` y su
equivalente `mex-`). Deduplicar con `QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY
createdate DESC) = 1`: un deal por nid, el más reciente.

Es atribución **conservadora**: solo cuenta a quien el loop recreó en el backbone. Si alguien
recibió el mensaje y volvió por su cuenta por otro canal, no aparece. Está bien que sea así —
pero al presentar el número, decirlo.

## Filtro `fuente='WEB'`: casi inocuo, pero es un filtro

Descarta 1 cierre en cada línea (18 de 19 en iBuyer, 28 de 29 en inmobiliaria). No es la causa
de ninguna discrepancia grande, pero si buscas cuadrar números al detalle, ahí está.

## Tres fuentes, tres números: cuál usar

El mismo concepto da distinto según de dónde se lea, y esto ha causado confusión real:

| Fuente | Cierres del loop | Nota |
|---|---|---|
| HubSpot, solo iBuyer | 19 | **Incorrecto** — es el bug que documenta este archivo |
| HubSpot, unión de las dos líneas | 48 | Lo que deben reportar las queries de este repo |
| Tablas operativas de funnel | 61 | Medido el 2026-08-11 en un análisis ad-hoc |

Las cuatro tablas operativas son `sellers-main-prod.bi_mx.seguimiento_funnel_mex`,
`papyrus-data.habi_wh_bi.funnel_diarios_col`, `sellers-main-prod.bi_co.seguimiento_inmobiliaria_col`
y `sellers-main-prod.bi_mx.seguimiento_inmobiliaria_mex_copia`. Dan más cierres porque HubSpot
es un espejo con rezago y con criterios propios.

**Regla operativa:** el tablero reporta desde HubSpot con la unión de las dos líneas (48). Si
alguien presenta un número distinto hacia afuera, tiene que decir de qué fuente salió. No
mezclar fuentes en la misma tabla.
