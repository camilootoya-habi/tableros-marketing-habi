# Re-segmentación JTBD — Estudio de vendedores Tuhabi MX (GDV)

**Fecha:** 2026-06-29
**Dueño:** general (Camilo)
**Tipo:** tablero estático de análisis (`section: analysis`, `country: MX`)
**Slug propuesto:** `segmentacion-jtbd-mx`

## Contexto

GDV entregó a Tuhabi MX un estudio de segmentación (n=291 vendedores/intentaron vender,
CDMX/GDL/MTY, NSE alto). La agencia segmentó por **estilo de decisión** (P.5, frases
actitudinales) en 4 buyer personas: Isadora (Buscadora Liquidez Rápida, 34%), Emilia
(Negociadora Pragmática, 24%), Clara (Analista Precavido, 25%), Esteban (Orientado a
Estabilidad, 17%). La asignación vive en la variable `Op4Groupsv1` (1/2/3/4).

**Problema:** la segmentación de la agencia describe *cómo decide* la persona, no *qué
necesidad resuelve la venta*. Para Tuhabi (iBuyer cuyo valor es liquidez rápida) lo
accionable es el **Job To Be Done**: el motivo por el que se contrata la venta.

## Objetivo

Reconstruir las diapositivas de cruce de GDV pero cortadas por **JTBD** en lugar de por
las 4 personas, con total transparencia sobre cómo se asignó cada encuestado.

## Metodología JTBD (acordada)

- **Fuente:** P.4 (motivación de venta, RM) + P.22 (uso del dinero, RM), combinadas en un
  único pool de señales por encuestado.
- **Taxonomía (4 jobs):**
  | Job | Señales P.4 | Señales P.22 |
  |---|---|---|
  | **Resolver una urgencia** | Gastos imprevistos, liquidez por salud, pagar deudas, remodelación no costeable, estudios hijos, aumento costos servicios, aumento inseguridad | Pagar deudas, Emergencia médica |
  | **Soltar un activo ocioso** | No habito la propiedad, herencia que no usaré, divorcio/separación de bienes | Repartir entre hijos/herencia, Rentar en otro lugar |
  | **Hacer rendir el capital** | Para invertir en otros activos, aumento de plusvalía, aproveché alta demanda | Invertir el dinero |
  | **Crecer / siguiente paso** | Mejor propiedad (tamaño/zona), crecimiento familiar, mudanza laboral | Comprar otra propiedad |
- **Membresía:** **penetración solapada** (no excluyente). Cada encuestado cuenta en
  TODOS los jobs que menciona; el % de un job = nº de vendedores que lo incluyen ÷ total.
  No suman 100%. (Se descartó el "job dominante por jerarquía" porque la jerarquía
  distorsionaba el retrato: inflaba Urgencia y hundía Crecer/Invertir — ver nota abajo.)

### Penetración por job (validado contra la base)

| Job | n | % de vendedores |
|---|---|---|
| Crecer / siguiente paso | 214 | 74% |
| Hacer rendir el capital | 133 | 46% |
| Resolver una urgencia | 118 | 41% |
| Soltar un activo ocioso | 96 | 33% |

(Suma 561 > 290 porque cada quien aporta a todos sus jobs.)

**Por qué penetración y no job dominante:** con jerarquía urgencia-primero, Crecer caía a
22% (63) y Urgencia subía a 41% (118) — invirtiendo el retrato real (Crecer es la
motivación más común; Invertir 46% > Urgencia 41%). El job dominante mentía. **Solapamiento:**
solo 93 (32%) mencionan un único job; 197 (68%) tienen 2+.

## Estructura del tablero (4 bloques)

1. **Metodología JTBD** — qué es, por qué re-segmentar por necesidad vs. estilo de decisión;
   las 4 jobs y la jerarquía.
2. **Transparencia de la asignación** — tamaños de segmento + distribución de # de jobs por
   persona (1/2/3/4) + matriz de co-ocurrencia entre jobs. Mensaje: "no son tipos de persona,
   son necesidades que conviven".
3. **Re-corte de slides por JTBD** — motor genérico que reproduce cada cruce de GDV cortado
   por las 4 jobs. Cobertura: P.1 necesidades de categoría/MaxDiff (slide 10), P.12 marca que
   usaría (13), P.28 barreras iBuyer (15), P.29 % descuento dispuesto (16), P.17 actitud
   plataformas (11), P.14 evaluación (19), P.26 medios (12). Cada cruce: tabla + chart +
   índice vs. total (resaltar índice ≥120%).
4. **Puente persona ↔ JTBD** — cómo se reparten las 4 personas de GDV dentro de cada job
   (matriz persona × job), para reinterpretar el trabajo de la agencia, no descartarlo.

## Datos y build

- Pipeline Python lee `BDD_Segmentación Tuhabi.xlsx` (hojas CODIGOS/ETIQUETAS/DATA MAP),
  computa la asignación JTBD y todos los cruces, y escribe `data.json`.
- Validación: reproducir primero los cruces por persona (`Op4Groupsv1`) y cotejar contra el
  PDF de GDV (slides 8/9/10) antes de re-cortar por JTBD.
- Tablero estático: sin `query.sql` (datos no vienen de BigQuery). `data.json` se commitea.
- Convenciones del hub: carpeta `<slug>/` en la raíz con `index.html` + `meta.json` +
  `data.json`. NO editar `index.html` raíz (generado). Selector estándar de filtros.

## Fuera de alcance

- Re-clustering data-driven (se eligió job dominante por jerarquía).
- Jobs solapados como audiencias no excluyentes (se documenta el solapamiento, pero los
  segmentos del tablero son excluyentes).
