# Métricas del Marketing Loop — definiciones canónicas

Este archivo existe porque el cierre se contó mal durante meses y el error es fácil de repetir:
la métrica *parece* correcta, la query corre sin fallar, y el número que sale es plausible.

Estado: el bug **ya está corregido** en las queries (commit `1f619b03`, 2026-08-21). Este doc
describe la definición vigente y por qué es así.

## 1. Cierre: DOS líneas de negocio, y cada PAÍS las guarda en campos distintos

Habi vende por dos vías, y —esto es lo que hace el bug tan escurridizo— **México y Colombia no
usan los mismos campos** de `sellers-main-prod.hubspot.deals`:

| Línea | Colombia | México |
|---|---|---|
| Compra directa (Market Maker) | `oportunidad_del_negocio = 'Cierre - Comprado'`, fechado por `closedate` | igual (los 10 coinciden exactamente con la etapa `'Firmado'`) |
| Inmobiliaria (red de aliados) | `oportunidad_inmobiliaria = 'Contrato firmado'`, fechado por `fecha_captacion_inmobiliaria` | **`fecha_de_contrato_firmado_mx IS NOT NULL`** (etapa `'Contrato firmado'`) |

Datos que sostienen esto (medido 2026-08-21, población del loop deduplicada por nid):

- En **México `oportunidad_del_negocio` está vacío** en 2.475 de 2.485 leads: ese país lleva su
  funnel en la **etapa de HubSpot**, no en ese campo.
- En **México `oportunidad_inmobiliaria` tiene 0 deals**. Su línea inmobiliaria vive en la etapa
  `'Contrato firmado'` (21 deals) y en `fecha_de_contrato_firmado_mx` (31 deals — los 10 extra
  ya avanzaron a etapas posteriores como `'Publicado'` y `'Captado'`, o sea que también firmaron).
- Los campos son **perfectamente disjuntos por país**: CO tiene 29 `fecha_captacion_inmobiliaria`
  y 0 `fecha_de_contrato_firmado_mx`; MX lo inverso. Y ningún cierre de compra directa coincide
  con un cierre de inmobiliaria. Cero solapamiento en todas las combinaciones.

### Números correctos (2026-08-21)

| País | Compra directa | Inmobiliaria | Total correcto | Lo que reporta el tablero hoy |
|---|---|---|---|---|
| Colombia | 9 | 29 | **38** | 38 ✅ |
| México | 10 | **31** | **41** | 41 ✅ |
| **Total** | **19** | **60** | **79** | 79 ✅ |

El fix de `1f619b03` resolvió la línea inmobiliaria de Colombia y dejó la de México intacta,
porque cada país la guarda distinto. **Cerrado el 2026-08-21**: el `COALESCE` de las dos fechas
quedó aplicado en `query_kpis.sql`, `query_comparativa.sql` y `query_funnel.sql`, y el tablero
reporta los 79. Ese es el patrón a recordar: **cuando un número cuadra en
un país y no en el otro, sospecha del vocabulario, no del dato.**

### La forma correcta, en una sola expresión

Como los campos son disjuntos por país, **no hace falta un CASE por país** ni el join a
`deal_pipelines_stages`: basta coalescer las dos fechas de inmobiliaria.

```sql
-- Cierre de compra directa
IF(oportunidad_del_negocio = 'Cierre - Comprado', CAST(closedate AS DATE), NULL) AS f_cierre_mm,
-- Cierre de inmobiliaria: CO usa fecha_captacion_inmobiliaria, MX fecha_de_contrato_firmado_mx.
-- Nunca están pobladas las dos a la vez, así que el COALESCE cubre ambos países.
CAST(COALESCE(fecha_captacion_inmobiliaria, fecha_de_contrato_firmado_mx) AS DATE) AS f_cierre_inmo
```

Se usa **la fecha poblada y no la etiqueta de etapa** a propósito: la etapa se mueve y borra la
evidencia de que hubo firma (los 10 deals de MX en `'Publicado'`/`'Captado'` firmaron y ya no
dicen `'Contrato firmado'`), la fecha no. Además evita un join.

`'Ya vendio'` también existe como estado de `oportunidad_inmobiliaria`, pero hoy tiene **0
deals** y su semántica es ambigua (¿vendió con la red, o por su cuenta?). No se cuenta.

## 2. ⚠️ Los dos cierres NO son el mismo evento económico

Esto es lo más importante al reportar el número hacia afuera:

- **Compra directa** = Habi compró el inmueble. Es una transacción cerrada.
- **Inmobiliaria "Contrato firmado"** = el vendedor firmó el mandato de venta con la red. Es una
  **captación**, no una venta. De hecho `fecha_captacion_inmobiliaria` es la fecha que lo fecha,
  y el nombre no es casualidad.

Verificado el 2026-08-21 sobre los 29 contratos del loop:

| | Colombia | México |
|---|---|---|
| Contratos firmados | 29 | 31 |
| Publicados | **0** | 4 (etapa `'Publicado'`) |
| Con fecha de venta | **0** | 0 |

En Colombia ninguno se ha publicado ni vendido. En México al menos 4 avanzaron a `'Publicado'`,
así que esa línea está algo más madura — pero tampoco hay ventas registradas. Así que **"38 cierres en Colombia" no significa 38
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

Cubre los dos países. Si tu número se parece a `compra_directa` en vez de a `total`, te falta
inmobiliaria; si MX te da 10, te falta la línea mexicana.

```sql
WITH d AS (
  SELECT * FROM `sellers-main-prod.hubspot.deals`
  WHERE country IN ('México','Colombia') AND utm_campaign LIKE '%reinteresados%'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nid ORDER BY createdate DESC) = 1
)
SELECT CASE country WHEN 'México' THEN 'MX' ELSE 'CO' END AS pais,
  COUNTIF(oportunidad_del_negocio = 'Cierre - Comprado') AS compra_directa,
  COUNTIF(COALESCE(fecha_captacion_inmobiliaria, fecha_de_contrato_firmado_mx) IS NOT NULL) AS inmobiliaria,
  COUNTIF(oportunidad_del_negocio = 'Cierre - Comprado'
          OR COALESCE(fecha_captacion_inmobiliaria, fecha_de_contrato_firmado_mx) IS NOT NULL) AS total
FROM d GROUP BY 1 ORDER BY 1
-- Esperado al 2026-08-21: CO 9 / 29 / 38 · MX 10 / 31 / 41
```

## 6. Tres fuentes, tres números: cuál usar

El mismo concepto da distinto según de dónde se lea, y esto ya causó confusión real:

| Fuente | Cierres del loop | Estado |
|---|---|---|
| HubSpot, solo compra directa | 19 | **Incorrecto** — el bug que corrigió `1f619b03` |
| HubSpot, unión de las dos líneas, solo vocabulario CO | 48 | Lo que reporta el tablero hoy — **le falta la línea inmobiliaria de MX** |
| HubSpot, unión con el vocabulario de AMBOS países | **79** | **Lo correcto** (CO 38 + MX 41) |
| Tablas operativas de funnel | 61 | Análisis ad-hoc del 2026-08-11, no versionado. Su MX (33) era correcto: eran los 10 firmados + los contratos de inmobiliaria que el tablero no ve |

Las cuatro tablas operativas son `sellers-main-prod.bi_mx.seguimiento_funnel_mex`,
`papyrus-data.habi_wh_bi.funnel_diarios_col`,
`sellers-main-prod.bi_co.seguimiento_inmobiliaria_col` y
`sellers-main-prod.bi_mx.seguimiento_inmobiliaria_mex_copia`. Dan más porque HubSpot es un
espejo con rezago y criterios propios. **Ninguna está referenciada en el código**: cualquier
cálculo desde ellas es ad-hoc y no reproducible con un comando.

**Regla operativa:** el tablero es la fuente oficial (HubSpot, dos líneas). Quien presente otro
número dice de qué fuente salió, y no se mezclan fuentes en la misma tabla.
