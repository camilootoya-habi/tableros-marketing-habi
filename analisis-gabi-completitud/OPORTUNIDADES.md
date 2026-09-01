# Oportunidades: completitud del funnel de Gabi (MX)

**Fecha:** 2026-09-01 · **Ventana medida:** conversaciones con `last_activity` 2026-06-01 → 2026-08-31
**Fuente:** `sellers-main-prod.chatbots.mabi_mx` (+ `gabi_mx` y `gabi_inmo_mx` para desenlace) · solo lecturas vía `bq`
**Cohorte:** bot B guionado (apertura "Recibimos tu solicitud", lanzamiento 2026) — **9.076 deals** (1 conversación = 1 `deal_id`, última ejecución, mensajes agregados por HORA como en `queries/funnel_etapas.sql`).

Retoma el análisis del 28-ago (`queries/`): allí quedó establecido *cualitativamente* (n=4) que el punto
de fuga es la **re-pregunta de m²**. Este documento lo cuantifica, mapea el drop-off de TODO el funnel
y lo cruza con desenlace de negocio. Spoiler honesto: la re-pregunta de m² es real, pero al medirla
resultó ser la **cuarta** oportunidad por tamaño — la etapa **dirección** es la fuga grande.

---

## 1. Completitud por etapa (la tabla que da nombre al análisis)

Etapas del bot B: apertura → tipo (casa/depto) → dirección (estado+calle+número+CP en texto) →
bloque de 6 datos (antigüedad, m², recámaras, baños, cajones, precio) → re-preguntas de faltantes → evaluación.

| Etapa alcanzada | Deals | % del total | Muere aquí | % de la etapa |
|---|---|---|---|---|
| Recibió apertura | 9.076 | 100% | 5.325 nunca respondieron | 58,7% |
| Respondió algo | 3.751 | 41,3% | 532 mueren en *tipo* | 14,2% |
| Llegó a *dirección* | 3.219 | 35,5% | **1.571 mueren en dirección** | **48,8%** |
| Entregó dirección → le piden el bloque | 1.695 | 18,7% | 448 mueren ante el bloque | 26,4% |
| Respondió el bloque de 6 | 1.237 | 13,6% | 147 mueren en re-pregunta de m² | 11,9% |
| Completó / pasó las re-preguntas | 1.060 | 11,7% | — | — |

(`queries/funnel_etapas.sql` y `queries/muerte_por_etapa_desenlace.sql`; las filas de "muere aquí" son
la clasificación mutuamente excluyente de la segunda query.)

**Cruce con desenlace** (deal aparece después en `gabi_mx` = agenda ibuyer, o `gabi_inmo_mx` = inmobiliaria):

| Muere en… | Deals | % ruteado a agenda/inmo |
|---|---|---|
| nunca respondió | 5.325 | 4,4% |
| tipo | 532 | 12,8% |
| **dirección** | **1.571** | **16,2%** |
| ante el bloque de 6 | 448 | 51,8% |
| re-pregunta de m² | 140 | 72,9% |
| completó/pasó | 1.060 | 79,1% |

El ruteo posterior crece monótonamente con la profundidad alcanzada. El salto más violento es
**dirección → bloque: 16,2% → 51,8% (+35,6 pp)**. ⚠ Es correlación (quien avanza más ya venía más
motivado), no efecto causal de completar la etapa — ver §5.

## 2. El hallazgo de m², ahora con números

De los 1.237 que respondieron el bloque de 6 datos:

- a **586 (47,4%)** Gabi les re-preguntó al menos un dato faltante (`queries/reask_por_campo.sql`);
- los datos que faltan son **área construida (30,2%)** y **precio (29,1%)** — lejos, los dos peores;
  cajones 17,9%, baños 9,6%, antigüedad 9,2%, recámaras 7,9%. m² y precio suelen faltar juntos;
- a **374 (30,2%)** les re-preguntaron el área construida: **147 (39,3%) no volvieron a escribir
  (MURIO_EN_M2)** y 227 (60,7%) la dieron (PASO_M2) (`queries/m2_cohortes_desenlace.sql`);
- ritmo estable: MURIO_EN_M2 ≈ **49/mes** (jun 49, jul 53, ago 45).

Los muertos en m² eran usuarios de alta intención: ya habían dado tipo, dirección y ~4-5 de los 6
datos. Muestreo manual de 5 colas (rendidas con `queries/show.py`): todos son muertes genuinas tras
"Solo me falta el *área construida*…" (a veces junto con precio) — cero falsos positivos en la muestra.
Confirma el hallazgo del 28-ago: **la fricción es la re-pregunta, no el dato** (el usuario no tiene el
m² a la mano — "suele venir en las escrituras" — y no vuelve).

**Pero el desenlace matiza el valor:** el ruteo posterior a agenda es **idéntico** en las tres cohortes
(59,9% DIO_TODO / 59,9% PASO_M2 / 59,9% MURIO_EN_M2 — sí, las tres; verificado con conteos crudos
517/863, 136/227, 88/147). Es decir: **la operación re-engancha al deal aunque el chat muera**, y lo
que se pierde al morir en m² no es el deal sino la **valuación completa en el chat** (el rechazo/filtro
por cobertura solo ocurre con datos: 9,4% en DIO_TODO vs 0% en MURIO_EN_M2) y el costo/latencia de
recuperarlo por otros canales. En deals ruteados, recuperar la mitad de los 147 vale ≈ +6 pp × 25/mes
≈ **+1-2 deals ruteados/mes**: pequeño. En evaluaciones completas tempranas vale ≈ **+25/mes**.

## 3. Oportunidades priorizadas (volumen perdido × cercanía a conversión)

### #1 — Dirección: dejar de pedir 4 campos de texto (≈524 muertes/mes)
La etapa dirección mata 1.571 conversaciones en el trimestre — **48,8% de quienes llegan ahí**, la
peor tasa de todo el funnel conversacional y 3× el volumen de todas las demás etapas post-respuesta
juntas. Desglose (`clasificación en §queries/muerte_por_etapa_desenlace.sql`, muestreos manuales):
1.079 nunca intentaron darla tras el pedido "estado + calle + número exterior + código postal";
486 la dieron parcial y murieron en el loop de aclaración ("¿me confirmas el código postal?",
"Reviso bien calle y número y se lo comparto"); solo 6 fueron rechazo de cobertura.
**Qué probar:** (a) aceptar la **ubicación compartida de WhatsApp** como respuesta válida;
(b) pre-llenar con la dirección que el lead ya dejó en la solicitud web y pedir solo *confirmación*
(hipótesis a validar: ¿qué % de solicitudes trae dirección?); (c) tolerar dirección parcial y
re-preguntar únicamente el CP, con la misma regla anti-re-pregunta del punto #3.
**Tamaño:** si la mitad de esas muertes avanzara y ruteara como la etapa siguiente (51,8% vs 16,2%),
serían ≈ **+93 deals ruteados/mes** — techo optimista por el sesgo de selección (§5); incluso con la
mitad del delta real sigue siendo la palanca más grande del funnel conversacional.

### #2 — Apertura: 58,7% jamás responde (≈1.775 silencios/mes)
5.325 deals no contestaron ni el primer mensaje. Es el mayor volumen absoluto, pero el más lejano a
conversión (4,4% ruteado) y el más contaminado (número inactivo, plantilla no leída, lead frío).
**Qué probar:** A/B de plantilla de apertura + horario de disparo + un único re-toque a 24h. No
requiere tocar el flujo de datos; el experimento es barato y el n es enorme (~3.000/brazo/mes).

### #3 — Bloque de 6: pedir con ejemplos y aceptar aproximados (448 + 586 afectados/trimestre)
448 (26,4%) enmudecen ante el pedido de 6 datos de golpe, y 47,4% de los que sí responden dejan
huecos que fuerzan re-pregunta. Los huecos son casi siempre **m² y precio** — justo los dos datos
que exigen saber algo (escrituras, avalúo) en vez de recordarlo.
**Qué probar:** en el mensaje del bloque, acompañar m² y precio con sugerencias basadas en
comparables de la zona — exactamente lo que el bot A (LLM libre) ya hace hoy con el área
("*1. 20 m² · 2. 46 m² · elige la opción o indícame si es diferente*", ver `queries/conv_completa.clean.json`) —
y aceptar explícitamente "aproximado" ("si no lo sabes, dime un aproximado y seguimos").

### #4 — m²: nunca re-preguntar en mensaje aparte (≈49 muertes/mes)
El hallazgo original, confirmado: 39,3% de los re-preguntados por área construida mueren ahí.
**Qué probar:** si tras el bloque falta solo m² (o m²+precio), no bloquear el avance: ofrecer rango
sugerido con botones (estilo bot A), aceptar aproximado, y si aun así no responde, **seguir el flujo**
marcando el dato como pendiente para el humano — hoy la conversación se detiene en seco ahí.
**Tamaño honesto:** ≈ +25 evaluaciones completas/mes recuperando la mitad; en deals ruteados el delta
es chico (+1-2/mes) porque la operación ya re-engancha el 73% de estos deals por otros canales. Su
valor es dato de valuación completo, filtro de cobertura temprano y menos trabajo manual.

### #5 — Nudge específico en vez del genérico
Todas las muertes intermedias reciben el mismo "*Sigo pendiente de tu respuesta*" (~2h después) y
nada más. **Qué probar:** nudge que repita el dato puntual faltante con la ayuda correspondiente
(sugerencia de m², "mándame tu ubicación", botones), y un segundo toque a 24h. Aplica transversal a
#1, #3 y #4.

## 4. Reproducibilidad

Todas las queries corren con `bq query --use_legacy_sql=false --maximum_bytes_billed=20000000000`
(cada pasada completa de `mabi_mx` ≈ 2,4 GB):

- `queries/funnel_etapas.sql` — funnel acumulado por etapa + cohortes m² (tabla §1 arriba).
- `queries/muerte_por_etapa_desenlace.sql` — etapa de muerte (excluyente) × ruteo a agenda/inmo.
- `queries/m2_cohortes_desenlace.sql` — DIO_TODO / PASO_M2 / MURIO_EN_M2 con volumen mensual y desenlace.
- `queries/reask_por_campo.sql` — qué campo re-pregunta Gabi tras el bloque.
- `queries/m2.sql`, `queries/conv_m2.clean.json`, `queries/show.py` — la evidencia cualitativa original (28-ago).

## 5. Límites y qué habría que A/B-testear

- **Correlación ≠ causa.** El gradiente de ruteo por etapa (4,4% → 79,1%) mezcla efecto del funnel con
  auto-selección: quien da más datos ya venía más decidido. Los "tamaños" de §3 son techos. La
  confirmación exige A/B: brazo con ubicación-de-WhatsApp/dirección pre-llenada vs control (#1),
  bloque con sugerencias vs sin (#3/#4). Con ~400-500 muertes/mes en dirección, un A/B 50/50 detecta
  una mejora de 10 pp en semanas.
- **Marcadores regex sobre texto generado por LLM.** Gabi redacta variantes; los marcadores son
  genéricos y case-insensitive pero pueden dejar escapar frases raras. El muestreo manual de colas no
  encontró falsos positivos de MURIO_EN_M2, pero el conteo fino (140–153 según la población base y
  el orden de clasificación de etapas) se mueve ±4%.
- **"Ruteado" es aparición del deal en `gabi_mx`/`gabi_inmo_mx` en cualquier momento** (sin ventana);
  ~97% de las agendas son posteriores a la conversación de mabi, pero no distinguimos si la agenda
  prosperó. `schedule_date` está vacío para toda esta cohorte (26k valores en 697k filas históricas,
  ninguno aquí) y `business_opportunity_label` falta en ~89% de los deals (hallazgo del 28-ago):
  **no hay línea directa a cita/oferta/cierre desde estas tablas**. Cerrar esa brecha (join a HubSpot
  por `deal_id`) es el siguiente paso natural si alguna oportunidad avanza a negocio.
- **Solo bot B (2026).** El bot A ("de a uno") tiene otro funnel; la comparación A vs B ya está en el
  análisis del 28-ago (`queries/estrat.sql`, `queries/ruteo.sql`) y no se re-derivó aquí.
- Ventana jun–ago 2026; los volúmenes mensuales fueron estables (±8%), pero estacionalidad no evaluada.
