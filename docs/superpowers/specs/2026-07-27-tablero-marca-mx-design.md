# Tablero de Marca MX + generador de informes de impacto

**Fecha:** 2026-07-27
**Estado:** diseño aprobado por Camilo
**Repo:** `tableros-marketing`

## Contexto

El informe de impacto de la campaña de branding OOH móvil con Uber (MTY + GDL, Q1 2026) se
construyó a mano en un Google Doc. Cada actualización obliga a bajar datos de Ads Manager, GA4
y BigQuery, recalcular a mano y reescribir el texto. El resultado quedó congelado y sus cifras
no son auditables: la afirmación "la recordación declarada de Uber alcanza un 2% en marzo de
2026" no se reproduce con ninguno de los cortes evaluados (ver *Definiciones canónicas*).

El objetivo no es automatizar ese documento. Es tener un **tablero vivo de indicadores de marca
en México** — cómo evoluciona la recordación, el tráfico y la atribución declarada — y que el
informe de Uber sea un consumidor de ese tablero, no la fuente de los números. Cuando llegue la
siguiente campaña de medios masivos, el tablero ya está; solo se escribe el editorial.

Alcance decidido, **asimétrico por métrica** (2026-07-27):

- **Brand Lift: CO + MX.** El mismo driver y el mismo token cubren las dos cuentas
  (`act_205661715114408` MX y `act_770068953990542` CO), así que Colombia no cuesta trabajo extra.
- **Tráfico y exit poll: MX únicamente.** El exit poll de CO vive en otro esquema
  (`papyrus-data.habi_db.tabla_contacto_v2.fuente_conocio_habi`) y no hay export de GA4 usable para
  CO — el WBR 2.0 ya resuelve tráfico CO por Segment. Completar CO es un proyecto aparte.

La asimetría hay que hacerla **visible en el tablero**: quien vea Brand Lift de CO y no encuentre su
exit poll tiene que entender que falta la fuente, no que el dato sea cero. Un estado vacío explícito
por métrica y país, no una serie en cero.

## Objetivos

1. Tablero de marca MX con tres indicadores en serie mensual: Brand Lift de Meta, tráfico y CPV
   por plaza, y atribución declarada del exit poll.
2. Generador de ediciones mensuales del informe de Uber: capítulos fijos, editorial versionado,
   cifras horneadas, ediciones pasadas inmutables.
3. Definiciones canónicas escritas y reproducibles para cada métrica.

## No-objetivos

- Colombia (ver arriba).
- Atribución causal de la campaña. El informe se sostiene explícitamente como medición de
  *Brand Equity*, no de respuesta directa; no se va a calcular un CPL de Uber.
- Escritura automática del editorial. Los capítulos de rigor operativo, amplificación, propuesta
  económica y conclusión los escribe una persona.

## Arquitectura

Dos carpetas independientes, dos cards en el hub. El tablero es el activo permanente; el informe
es un consumidor que hornea snapshots.

```
marca-mx/                          ← TABLERO VIVO (section: dashboard)
├── meta.json                      ← sin `query`; el cron lo corre por build.py
├── build.py                       ← orquesta los 3 drivers → data.json
├── queries/trafico_plazas.sql     ← GA4 usuarios activos + inversión → CPV por plaza/mes
├── queries/exit_poll.sql          ← donde_nos_conociste por mes × plaza × opción
├── brand_lift_cache.json          ← histórico cacheado y versionado (ver rate limit)
├── questions.json                 ← experiment_id → pregunta
├── index.html                     ← tablero (Chart.js + selector estándar de chips)
└── data.json                      ← generado

informe-uber-ooh/                  ← EL DOCUMENTO (section: analysis)
├── meta.json + build.py + render.py + plantilla.html
├── contenido/base/NN-capitulo.md  ← editorial: un Markdown por capítulo
├── contenido/2026-07/NN-*.md      ← lo que cambia ese mes (reemplaza o agrega)
├── assets/                        ← mapas de zonas MTY/GDL, fotos de flota
├── index.html                     ← índice: última edición + archivo
└── 2026-07/index.html             ← edición (se congela sola al cambiar de mes)

scripts/probe_meta_brandlift.py    ← sonda de una sola vez para decidir el driver de Brand Lift
```

Por qué esta frontera: el tablero contesta "cómo va la marca" y sobrevive a cualquier campaña.
El informe contesta "qué logró Uber" y tiene fecha de caducidad. Mezclarlos obligaría a reescribir
el tablero cada vez que cambie la narrativa de una campaña.

### Encaje con el hub (verificado en código)

- `scripts/build_hub.py::discover_dashboards` recorre `rglob("meta.json")` y arma el link con la
  ruta relativa completa, así que ambas carpetas generan card sin tocar nada más. Las subcarpetas
  de edición (`2026-07/`) **no llevan `meta.json`** — si lo llevaran, cada mes generaría una card.
- `scripts/run_queries.py::discover_jobs` corre `build.py` con `cwd` en la carpeta del tablero
  cuando existe (escape hatch ya soportado). No hay que agregar steps a `update-data.yml`.
- `index.html` de la raíz es generado: no se edita a mano. El orden en su sección se controla con
  `order` en `meta.json`.

## Definiciones canónicas

| Indicador | Fuente | Definición |
|---|---|---|
| **Brand Lift / Ad Recall** (CO + MX) | Meta Marketing API | `scoreMean.test` (expuesto), `scoreMean.control`, `scoreMean.incremental` (lift en puntos), + intervalo de confianza. Serie mensual por país y por pregunta. |
| **Tráfico por plaza** | `papyrus-data-mx.analytics_325611813` | `COUNT(DISTINCT user_pseudo_id)` por mes × plaza vía `geo.region`, sin filtro de engagement. Desvía ±25% de la UI de GA4; desviación ya aceptada en trabajos previos y se anota en el tablero. |
| **CPV** | `sellers-main-prod.bi_mx.resumen_inversiones_regiones_mexico` | spend de la plaza ÷ usuarios activos de la plaza. **Mensual** — esa tabla no tiene granularidad diaria ni clicks/impresiones, así que el CPV es una métrica mensual por diseño, no una elección. |
| **Exit poll — tasa de respuesta** | `papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general` | respuestas no vacías de `donde_nos_conociste` ÷ registros con `fuente_id = 3` (WEB), por mes. |
| **Exit poll — share por opción** | idem | respuestas de la opción ÷ respuestas totales del mes. Cortes: nacional y por plaza. |

Plazas y su llave en cada fuente. Las tres fuentes nombran las plazas distinto, así que el mapeo
vive en un solo diccionario en `build.py` y no se repite en cada query:

| Plaza | Exit poll (`estado_mexico`) | GA4 (`geo.region`) | Inversión (`area_metropolitana`) |
|---|---|---|---|
| MTY | `Nuevo Leon`, `Nuevo León` | `Nuevo Leon` | `Zona metropolitana Monterrey` |
| GDL | `Jalisco` | `Jalisco` | `Zona metropolitana Guadalajara` |
| CDMX | CDMX + Estado de México | por verificar | `Valle de México` |
| Resto | resto | resto | resto |

La variante con y sin tilde de Nuevo León debe cubrirse siempre. **CDMX queda por verificar en la
implementación**: `Valle de México` en la tabla de inversión agrupa CDMX con Estado de México,
mientras GA4 los separa en regiones distintas. Hay que igualar los dos lados antes de dividir, o
el CPV de CDMX sale inflado.

### Trap: no usar las tablas regionales de `papyrus-data-mx`

`habi_wh_bi.resumen_inversiones_region_mx`, `habi_wh_bi.facebook_region_mx` y
`habi_wh_bi.google_region_mx` **están muertas: las tres cortan en 2024-04-25**. Son la primera
cosa que aparece al buscar "inversión regional MX" y devuelven cero filas para el periodo de la
campaña sin lanzar ningún error — una query contra ellas produce un CPV vacío que parece un bug de
la query. La fuente viva es `sellers-main-prod.bi_mx.resumen_inversiones_regiones_mexico`, con
datos hasta 2026-07 verificados.

`resumen_inversiones_mkt_mx` (la que usan WBR 2.0, OKR y funnel-web-mx) **sí está viva pero no
tiene plaza** — sirve para inversión nacional, no para CPV por ciudad.

### Evidencia recolectada al diseñar (2026-07-27)

El denominador WEB es lo que reproduce la tasa de respuesta del Google Doc original ("entre 71% y
83%"). Serie verificada:

| | oct-25 | nov | dic | ene-26 | feb | mar | abr | may | jun | jul |
|---|---|---|---|---|---|---|---|---|---|---|
| Tasa de respuesta (WEB) | 71.5% | 71.0% | 71.8% | 77.1% | 78.3% | 78.9% | 72.3% | 79.0% | 68.9% | 62.7% |
| Share Uber nacional | 0.00% | 0.21% | 0.40% | 0.40% | 0.46% | 0.63% | 0.53% | 1.12% | 1.23% | 1.83% |
| Share Uber MTY+GDL | 0.00% | 0.42% | 0.43% | 0.62% | 1.28% | 1.62% | 1.04% | 2.09% | 2.47% | 2.56% |

**Discrepancia resuelta por decisión:** el "2% en marzo de 2026" del doc original no se reproduce
(marzo da 1.62% en MTY+GDL y 0.63% nacional). El 2% se alcanza en mayo. La primera edición publica
la serie recalculada con una nota al pie indicando que la cifra previa correspondía a otro corte.
Se prefiere una serie reproducible sobre una cifra que no se puede auditar; la serie recalculada
además sostiene mejor el argumento, porque sigue subiendo hasta julio sin señal de saturación.

## Componentes

### 1. Ingesta con drivers intercambiables

`marca-mx/build.py` corre tres drivers independientes y **aísla fallos**: si uno revienta, los
otros dos escriben su parte de `data.json` (mismo criterio que `run_queries.py`, que ya aísla por
tablero). Cada indicador en `data.json` lleva `source` (`"bq" | "api" | "csv"`) y `last_updated`.

El tablero muestra un badge cuando un indicador viene de carga manual y su `last_updated` está
vencido. Sin ese badge, un CSV que nadie actualizó se ve idéntico a un dato fresco — que es
exactamente el modo de falla que hace que un tablero pierda credibilidad.

### 2. Driver de Brand Lift — driver `api` CONFIRMADO (probado 2026-07-27)

La sonda contra la cuenta de MX confirmó que los resultados de encuesta se leen por API. Detalle
completo de endpoints y campos en la memoria `habi/meta_brand_lift_api.md`; lo que importa para el
diseño:

- Ruta: `GET /{ad_account}/ad_studies` (edge con guion bajo) → filtrar `type == "LIFT"` →
  `GET /{study_id}/objectives` → **`GET /{objective_id}?fields=results`**.
- `results` es una **lista de strings**, cada uno un JSON que hay que parsear aparte. Una entrada
  por `experiment_id`, que equivale a una pregunta de encuesta.
- De ahí sale `scoreMean.test` (expuesto), `scoreMean.control`, `scoreMean.incremental` (lift en
  puntos), el intervalo de confianza, `responders.*` y `spend`. Y de gratis, dos benchmarks que no
  teníamos: `scoreMeanRegion` y `scoreMeanVertical`.
- Credenciales: el System User **AgenteMarketing** del BM de Habi ya existente, con `ads_read` ya
  concedido. No hay que crear token nuevo. Ve las cuentas de MX **y CO**.

**Hay 39 estudios LIFT en MX desde julio 2022**, mensuales recurrentes, con ~4 preguntas cada uno
— cuatro años de serie, no los 8 meses del doc original.

#### El rate limit manda la arquitectura del driver

Recorrer los 39 estudios completos son ~100 llamadas y **tumba la cuota** del tier "Limited"
(~300 + 40×ads activas por hora, por cuenta): error 613 / subcode 1487742, `is_transient: true`.
Se comprobó en la sonda, no es teórico.

Por eso el driver es incremental, no un barrido:

1. **Backfill una sola vez** a `brand_lift_cache.json`, versionado en el repo, corrido a mano y con
   pausas. Es el histórico completo y no se vuelve a bajar.
2. **En cada corrida del cron**, refrescar solo el mes en curso y el anterior. Un estudio cuyo
   `end_time` ya pasó es inmutable: nunca se re-consulta.
3. Ante error `is_transient`, backoff y conservar el caché. Un rate limit no debe vaciar la serie.

El caché versionado también es el seguro: si mañana Meta cierra el acceso, la serie histórica ya
está en el repo y el tablero sigue mostrando todo menos el mes nuevo.

#### Reglas de trato con la cuenta publicitaria (no negociables)

`act_205661715114408` es la cuenta donde vive la pauta de Habi México en producción. La cuota de
API es **compartida por cuenta**: agotarla no degrada la entrega de anuncios, pero sí throttlea a
cualquier otra integración que consulte esa cuenta en la misma ventana. El 2026-07-27 se agotó con
un barrido exploratorio de ~120 llamadas — el incidente que motiva estas reglas.

1. **Presupuesto de llamadas explícito y escrito** antes de cada corrida nueva. Ninguna exploración
   "a ver qué devuelve" contra esta cuenta.
2. **Toda respuesta se persiste a disco antes de mirarla.** Nunca `| head` sobre una respuesta de
   API: trunca el output y obliga a repetir la llamada. La llamada se paga una vez.
3. **Nada se re-consulta.** Un estudio con `end_time` en el pasado es inmutable; si está en el
   caché, no se vuelve a pedir jamás.
4. **Techo duro por corrida** en el driver, y `sleep` entre llamadas. Al primer `is_transient`,
   aborta y conserva el caché.
5. **Solo lectura a nivel de activo.** El System User debe tener "Ver rendimiento" sobre esta
   cuenta, no "Administrar campañas" — aunque el token traiga scope `ads_management` por el
   proyecto de pauta. El permiso del activo es lo que de verdad limita.
6. El backfill histórico se corre **una vez, a mano, supervisado**. Nunca desde el cron.

#### Pendiente de la sonda: mapear pregunta ↔ `experiment_id`

Cada estudio trae ~4 preguntas y el `experiment_id` **cambia cada mes**, así que no sirve de llave
estable. Los `results` no traen etiqueta de pregunta. Dos vías, en orden:

1. Introspección con `?metadata=1` sobre el objective para ver si hay un campo con el texto de la
   pregunta (quedó sin correr por el rate limit).
2. Si no hay etiqueta: identificar cada pregunta **por sus valores**, cruzando sep-2025 → mar-2026
   contra la serie de TOMA ya documentada del informe MTY (sep 14.07/8.33 … mar 20.07/11.55) y
   contra el Ad Recall del informe Uber (máximo expuesto 33.6%, lift máximo +16.3).

Las cuatro preguntas se distinguen además por su firma: una tiene ~1000 responders (el doble de las
otras) y lift típicamente negativo; otra vive en 5–10% de tasa base. **Esto hay que resolverlo
antes de graficar cualquier cosa** — publicar la pregunta equivocada como "Ad Recall" es peor que
no publicar. En julio 2026, de las dos preguntas leídas, una da +11.2 pts y la otra −4.8.

### 3. Generador de ediciones

**Un archivo Markdown por capítulo**, no un YAML. Dos razones: el runner del cron no tiene `pyyaml`
(el workflow no instala dependencias), y escribir prosa ejecutiva en bloques YAML es un dolor de
indentación y escapes. Con un `.md` por capítulo los diffs de Git son legibles y se edita con
herramientas normales.

```
contenido/base/01-resumen-ejecutivo.md   ← capítulos estables
contenido/base/02-rigor-operativo.md
contenido/2026-07/07-propuesta.md        ← solo lo del mes
```

El prefijo numérico da el orden. Un archivo del mes con el **mismo nombre** que uno de `base`
lo reemplaza; con un **nombre nuevo**, agrega capítulo. Para el informe de agosto se escribe solo
lo que cambia.

**Cómo el editorial cita datos:** el texto lleva `{{metrica.pais.campo.latest:formato}}` y el
render lo sustituye desde `data.json`. Así una cifra del informe no puede divergir del tablero,
porque no hay números escritos a mano. **Un placeholder que no resuelve aborta el render** — nunca
se emite `{{...}}` literal ni un cero silencioso en un documento que va a comité. Si la métrica está
en `not_available`, citarla es un error de autoría y falla ruidosamente.

**Cómo el editorial pide gráficas:** una valla ` ```chart ` con `clave: valor` dentro del capítulo,
que el render convierte en un canvas. La gráfica vive donde vive el texto que la explica.

`build.py` renderiza **solo** la carpeta del mes actual. Al cambiar el mes, la anterior deja de
tocarse y queda inmutable por construcción — el documento vivo se sella a sí mismo, sin un paso
manual que alguien pueda olvidar. Flag `--freeze YYYY-MM` para sellar antes.

Las cifras se hornean al HTML de la edición. Una edición pasada no depende de nada externo: se abre
en dos años y muestra lo mismo. Por eso las funciones de dibujo se **copian** a la plantilla en vez
de importarse del tablero.

### 4. Capítulos del informe

Ocho capítulos fijos, heredados del doc original. Origen de cada uno:

| Cap | Contenido | Origen |
|---|---|---|
| 1 | Resumen ejecutivo | cifras del tablero + narrativa editorial |
| 2 | Rigor operativo y brand safety | editorial + `assets/` (mapas de zonas) |
| 3 | Estrategia de amplificación | editorial (conteo de Reels, links a Drive) |
| 4 | Brand Lift de Meta | tablero |
| 5 | Sinergia brand ↔ performance (tráfico y CPV) | tablero |
| 6 | Validación de atribución (exit poll) | tablero |
| 7 | Propuesta de continuidad | editorial (precios Bullmedia) |
| 8 | Conclusión de inversión | editorial |

El tono sigue el estándar de informes de marketing ya establecido: audiencia ejecutiva, sin jerga,
y cuando una campaña muestra señal real pero modesta frente a la inversión, se argumenta el
impacto positivo y se explicita el ROI bajo.

## Manejo de errores

- Fallo de un driver: se registra, los demás continúan, el indicador conserva su último valor en
  `data.json` con su `last_updated` viejo y el tablero lo marca como vencido.
- Query de BQ sobre el tope de bytes: `maximum_bytes_billed` por tablero en `meta.json` (default
  5 GB en `run_queries.py`). Las queries se acotan por rango de fecha, no escanean historia
  completa cada corrida.
- Token de Meta expirado (60 días): el driver `api` degrada a `csv` en lugar de tumbar el build.

## Fases

El tablero es prerequisito del informe, así que la implementación va en dos fases con un punto de
revisión entre ellas:

1. **`marca-mx`** — los tres drivers, `data.json`, el tablero y sus filtros. Al terminar esta fase
   ya hay valor entregado, exista o no el informe.
2. **`informe-uber-ooh`** — `content.yaml`, render, congelado, índice de ediciones. Depende de que
   `data.json` esté estable.

El probe de Brand Lift corre antes de la fase 1 porque decide qué driver se construye.

## Verificación

Revisión en `localhost:8091` antes de cualquier push. Cuatro comprobaciones con datos, no de vista:

1. La tasa de respuesta del exit poll reproduce la tabla de evidencia de arriba (71–79% en el
   rango oct-25 → may-26).
2. La serie de tráfico de MTY empata con el chart del informe MTY Multimedios ya validado.
3. El CPV de CDMX no se infla por el desajuste `Valle de México` ↔ GA4 (ver mapeo de plazas).
4. Congelar julio, regenerar agosto, y confirmar con `git diff` que el HTML de julio no cambió un
   solo byte.

**Verificación de IAM antes de codificar la query de CPV:** el cron autentica con
`GCP_CREDENTIALS` y `GCP_PROJECT=papyrus-data`. Otros tableros ya leen de `sellers-main-prod`
(el WBR 2.0 consulta `sellers-main-prod.*_segment_profiles.pages` desde el cron), pero eso no
garantiza el dataset `bi_mx` en particular — ya hubo casos de datasets inaccesibles desde el
workflow. Hay que correr la query desde una ejecución del workflow, no solo desde local, antes de
darla por buena.

## Pendiente externo (fuera de código)

Camilo genera un System User token en el Business Manager de Habi con scope `ads_read` para correr
el probe de Brand Lift. Todo lo demás avanza sin ese token.
