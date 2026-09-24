# Encargo: falta la línea inmobiliaria de MÉXICO en los cierres

**Estado: ✅ HECHO** (código en `a617d38b` el 2026-08-21; verificado y cerrado el 2026-08-31).
El COALESCE de las dos fechas quedó aplicado en `query_kpis.sql`, `query_comparativa.sql`,
`query_funnel.sql` (y `query_panel.sql`), y el tablero reproduce la definición canónica.

**Verificación del 2026-08-31** (query canónica de abajo, corrida contra
`sellers-main-prod.hubspot.deals`, y la misma cifra ±0 en la query del tablero y en `data.json`):

| País | Compra directa | Inmobiliaria | Total |
|---|---|---|---|
| CO | 11 | 35 | **46** |
| MX | 13 | 35 | **48** |
| **Total** | **24** | **70** | **94** |

⚠️ Al reportar hacia afuera, decir la composición: los 94 son **24 compras cerradas + 70
mandatos de captación inmobiliaria firmados** (no ventas). Tratarlos igual en cálculos de
ahorro o costo por cierre sobrevende — ver advertencia 1 al final.

---

Lo que sigue es el encargo original, conservado como contexto.

**Estado (histórico):** pendiente. El fix de `1f619b03` (2026-08-21) corrigió la línea inmobiliaria de
**Colombia** y dejó la de **México** afuera, porque cada país la guarda en campos distintos.

**Impacto:** el tablero reportaba 10 cierres de MX cuando eran **41** (al corte 2026-08-21). Faltaban 31.

## Dónde mirar en México

México **no usa** los campos de Colombia:

| Campo | En MX |
|---|---|
| `oportunidad_del_negocio` | vacío en 2.475 de 2.485 leads del loop (solo 10 lo traen) |
| `oportunidad_inmobiliaria` | **0 deals**. México no usa este campo |

México lleva el funnel en la **etapa de HubSpot** y en fechas propias:

| Concepto | Señal en MX | Deals |
|---|---|---|
| Compra directa | `oportunidad_del_negocio='Cierre - Comprado'` (= etapa `'Firmado'`, mismos 10) | 10 |
| **Inmobiliaria** | **`fecha_de_contrato_firmado_mx IS NOT NULL`** | **31** |
| (etapa equivalente, menos robusta) | etapa `'Contrato firmado'` | 21 |

Los 10 de diferencia entre 31 y 21 son deals que **ya avanzaron** a etapas posteriores
(`'Publicado'` 4, `'Captado'` 4, y otros): firmaron igual, pero la etiqueta de etapa ya cambió.
Por eso se usa **la fecha poblada y no la etapa**: la etapa se mueve y borra la evidencia, la
fecha no. Bonus: evita el join a `deal_pipelines_stages`.

## El cambio

Los campos son **disjuntos por país** (verificado: CO tiene 29 `fecha_captacion_inmobiliaria` y
0 `fecha_de_contrato_firmado_mx`; MX lo inverso; cero solapamiento con compra directa). Así que
**no hace falta un CASE por país**: un COALESCE cubre los dos.

En `query_kpis.sql`, `query_comparativa.sql` y `query_funnel.sql`, reemplazar la expresión de
cierre de inmobiliaria:

```sql
-- ANTES (solo Colombia)
IF(oportunidad_inmobiliaria='Contrato firmado', CAST(fecha_captacion_inmobiliaria AS DATE), NULL) AS f_cierre_inmo

-- DESPUÉS (CO + MX)
-- CO usa fecha_captacion_inmobiliaria, MX fecha_de_contrato_firmado_mx. Nunca están pobladas
-- las dos a la vez, así que el COALESCE cubre ambos países sin CASE ni join a etapas.
CAST(COALESCE(fecha_captacion_inmobiliaria, fecha_de_contrato_firmado_mx) AS DATE) AS f_cierre_inmo
```

En el funnel por cohorte, el flag equivalente:

```sql
IF(COALESCE(fecha_captacion_inmobiliaria, fecha_de_contrato_firmado_mx) IS NOT NULL, 1, 0) AS cierre_inmo
```

La expresión de compra directa **no cambia**: `oportunidad_del_negocio='Cierre - Comprado'`
fechado por `closedate` funciona igual en los dos países.

## Verificación

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
```

**Esperado al 2026-08-21:** CO 9 / 29 / **38** · MX 10 / 31 / **41** · total **79**.
Si MX sigue dando 10, el cambio no entró.

## Al presentar el número, dos advertencias

1. **Un "contrato firmado" es una CAPTACIÓN, no una venta.** De los 29 de CO, 0 tienen fecha de
   publicación y 0 de venta; de los 31 de MX, 4 llegaron a `'Publicado'` y 0 a venta. Así que
   "79 cierres" son 19 compras cerradas + 60 mandatos de venta firmados. Sumarlos es lo pedido,
   pero decir la composición — sobre todo en cálculos de ahorro o costo por cierre, donde tratar
   un mandato igual que una compra infla el resultado.
2. **No filtres la cohorte del loop por `fuente='WEB'`**: recorta 419 leads propios (Web
   Scraping, Estudio Inmueble, Leadforms). La UTM ya define la cohorte. El filtro sí es correcto
   para el baseline "WEB nuevo".

Contexto completo y definiciones canónicas: `marketing-loop/METRICAS.md`.
