# Métricas del Marketing Loop — definiciones canónicas

Este archivo existe porque el cierre se contó mal durante meses y el error es fácil de repetir:
la métrica *parece* correcta, la query corre sin fallar, y el número que sale es plausible.

Estado: el bug **ya está corregido** en las queries (commit `1f619b03`, 2026-08-21). Este doc
describe la definición vigente y por qué es así.

## 1. Cierre: SIEMPRE son DOS líneas de negocio

Habi vende por dos vías y **cada una guarda su cierre en un campo distinto** de
`sellers-main-prod.hubspot.deals`:

| Línea | Campo y valor de cierre | Fecha con la que se fecha |
|---|---|---|
| Market Maker / compra directa | `oportunidad_del_negocio = 'Cierre - Comprado'` | `closedate` |
| Inmobiliaria / red de aliados | `oportunidad_inmobiliaria = 'Contrato firmado'` | `fecha_captacion_inmobiliaria` |

Contar solo `oportunidad_del_negocio` mide compra directa y **tira a la basura la línea de
aliados**. Medido el 2026-08-21 sobre la población del loop (`utm_campaign LIKE
'%reinteresados%'`, deduplicado por nid):

| País | Compra directa | Inmobiliaria | Unión (correcto) |
|---|---|---|---|
| Colombia | 9 | 29 | **38** |
| México | 10 | 0 | **10** |
| **Total** | **19** | **29** | **48** |

Solapamiento entre líneas: **cero**. En Colombia el error reportaba 9 de 38. En México es
**invisible** porque la línea inmobiliaria no opera allá dentro del loop — por eso el bug
sobrevivió meses: quien validaba mirando MX veía números correctos.

`'Ya vendio'` también es un estado de `oportunidad_inmobiliaria`, pero hoy tiene **0 deals** en
esta población y su semántica es ambigua (¿vendió con la red, o vendió por su cuenta?). Las
queries usan solo `'Contrato firmado'`. Si algún día aparece con volumen, hay que decidirlo
antes de sumarlo.

## 2. ⚠️ Los dos cierres NO son el mismo evento económico

Esto es lo más importante al reportar el número hacia afuera:

- **Compra directa** = Habi compró el inmueble. Es una transacción cerrada.
- **Inmobiliaria "Contrato firmado"** = el vendedor firmó el mandato de venta con la red. Es una
  **captación**, no una venta. De hecho `fecha_captacion_inmobiliaria` es la fecha que lo fecha,
  y el nombre no es casualidad.

Verificado el 2026-08-21 sobre los 29 contratos del loop:

| | Contratos inmobiliaria |
|---|---|
| Total | 29 |
| Con `fecha_publicacion_inmobiliaria` | **0** |
| Con `fecha_venta_inmobiliaria` | **0** |

Ninguno se ha publicado ni vendido todavía. Así que **"38 cierres en Colombia" no significa 38
casas vendidas**: son 9 compras cerradas + 29 mandatos firmados que aún no han producido venta.

El tablero muestra las columnas separadas (Cierre MM · Cierre Inmo · Cierre total) justamente
para que la mezcla esté a la vista. **Al presentar el número afuera —sobre todo en cálculos de
ahorro o de costo por cierre— hay que decir la composición**, o se está sobrevendiendo: el valor
económico de una compra cerrada y de un mandato de captación no es el mismo.

## 3. Población: la UTM define la cohorte, NO la fuente

Un lead es del Marketing Loop si su `utm_campaign` contiene `reinteresados`. Deduplicar con
`QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC) = 1`.

**No filtres la cohorte del loop por `fuente='WEB'`.** El loop también trae leads de Web
Scraping (352), Estudio Inmueble (48) y Leadforms (19): ese filtro recortaba **419 leads
propios**, un 9% de la población (4.049 en vez de 4.468), y con eso los leads creados YTD de MX
pasaban de 2.485 a 2.133. Afecta poco al conteo de cierres (1 por línea) pero mucho a
denominadores y tasas.

El filtro **sí** es correcto para el baseline "WEB nuevo", que por definición son leads del
sitio sin la UTM del loop.

Atribución conservadora: solo cuenta a quien el loop recreó. Si alguien recibió el mensaje y
volvió por otro canal, no aparece. Está bien que sea así — pero decirlo al presentar.

## 4. Fechas

`fecha_de_firma` **no sirve para nada**: está vacía en toda la tabla (0 de 3.287 cierres).

- Compra directa → `closedate` (poblado en los 19, ninguno nulo).
- Inmobiliaria → `fecha_captacion_inmobiliaria` (poblada en los 29; coincide ±1 día con
  `fecha_oportunidad_inmobiliaria` y `closedate`, así que la elección es semántica, no numérica).
- **KPI de cabecera** (MTD/WTD/YTD): filtra por esas fechas de cierre.
- **Funnel por cohorte**: NO filtra por fecha de cierre; agrupa por antigüedad de `createdate` y
  cuenta los cierres de esa gente, ocurran cuando ocurran. Los dos números son distintos **por
  diseño**; no intentes hacerlos coincidir.

## 5. Cómo verificar en 30 segundos

Si tocas cualquier query de cierres, corre esto. Si tu número se parece a `compra_directa` en
vez de a `union_ambas`, te falta la línea inmobiliaria.

```sql
WITH d AS (
  SELECT nid, country, oportunidad_del_negocio AS op_mm, oportunidad_inmobiliaria AS op_in
  FROM `sellers-main-prod.hubspot.deals`
  WHERE country IN ('México','Colombia') AND utm_campaign LIKE '%reinteresados%'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC) = 1
)
SELECT country,
  COUNTIF(op_mm = 'Cierre - Comprado')          AS compra_directa,
  COUNTIF(op_in = 'Contrato firmado')           AS inmobiliaria,
  COUNTIF(op_mm = 'Cierre - Comprado'
          OR op_in = 'Contrato firmado')        AS union_ambas
FROM d GROUP BY 1 ORDER BY 1
```

## 6. Tres fuentes, tres números: cuál usar

El mismo concepto da distinto según de dónde se lea, y esto ya causó confusión real:

| Fuente | Cierres del loop | Estado |
|---|---|---|
| HubSpot, solo compra directa | 19 | **Incorrecto** — el bug que corrigió `1f619b03` |
| HubSpot, unión de las dos líneas | 48 | **Lo que reporta el tablero hoy** |
| Tablas operativas de funnel | 61 | Análisis ad-hoc del 2026-08-11, no versionado |

Las cuatro tablas operativas son `sellers-main-prod.bi_mx.seguimiento_funnel_mex`,
`papyrus-data.habi_wh_bi.funnel_diarios_col`,
`sellers-main-prod.bi_co.seguimiento_inmobiliaria_col` y
`sellers-main-prod.bi_mx.seguimiento_inmobiliaria_mex_copia`. Dan más porque HubSpot es un
espejo con rezago y criterios propios. **Ninguna está referenciada en el código**: cualquier
cálculo desde ellas es ad-hoc y no reproducible con un comando.

**Regla operativa:** el tablero es la fuente oficial (HubSpot, dos líneas). Quien presente otro
número dice de qué fuente salió, y no se mezclan fuentes en la misma tabla.
