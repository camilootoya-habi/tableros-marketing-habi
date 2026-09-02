# Bugs y fallas del agente Gabi (MX)

**Fecha:** 2026-09-02 · **Ventana:** conversaciones jun–ago 2026 (misma cohorte que `OPORTUNIDADES.md`)
**Fuente:** `sellers-main-prod.chatbots.mabi_mx` vía `queries/export_conversaciones.sql` (una pasada, ≈2,4 GB)
**Cohorte:** bot B = **9.076** deals (3.751 con al menos una respuesta del usuario) · bot A = **868** (560 con respuesta).
Reproduce exactamente el funnel de `OPORTUNIDADES.md` §1 (5.325 / 532 / 1.571 / 448 / 140 / 1.060).
**Método:** 12 detectores sobre los 49.817 turnos (`bugs/detectores.py`, 62 tests), corridos con `bugs/run.py`;
**90 conversaciones leídas y etiquetadas a mano** (`bugs/validacion.csv`) para medir precisión por tipo.
**No se usó juez LLM:** requiere sacar conversaciones del entorno de Habi y esa decisión es de Nicolas, no del análisis.

---

## 1. Resumen ejecutivo

- **El bug con más volumen y más limpio es que Gabi reenvía mensajes.** 571 conversaciones del bot B (15,2%
  de las que respondieron) tienen un mensaje repetido; en particular **493 leads (5,4% de los 9.076) recibieron
  el mensaje de apertura dos o más veces**, y 219 de ellos nunca contestaron. Precisión validada: 10/10.
- **La segunda es que Gabi deja al usuario hablando solo:** 139 conversaciones de B (3,7%) y 121 de A (21,6%)
  terminan con un turno del usuario sin respuesta, o sólo con el nudge automático. Precisión 6/7. Aquí caen las
  preguntas de negocio sin responder ("¿Puede hacer una oferta?") y los últimos datos entregados al vacío.
- **El nudge se dispara mal en 45 conversaciones:** el usuario ya había contestado y aun así recibe
  "*Sigo pendiente de tu respuesta*". Sólo 2,2% de esas conversaciones rutea después, contra 19,0% del resto.
- **Cuando el usuario pide un humano o dice que no quiere vender, Gabi sigue el guion** (9 casos, precisión 4/4).
  Volumen chico pero es el peor tipo de falla de cara al cliente.
- **Hallazgo negativo importante: Gabi NO se traga las respuestas ambiguas.** En las 12 conversaciones que el
  detector marcó, las 12 veces Gabi había pedido aclaración o aceptado un aproximado. El detector se retira; la
  conclusión es que ese bug no existe con volumen medible.

---

## 2. Tabla de fallas

Todas las cifras son conversaciones **del bot B** salvo donde se indique. "% resp" es sobre las 3.751 que
respondieron al menos una vez (bot A: 560). El estatus sigue la regla fijada antes de medir: ≥80% de precisión
se reporta como cifra, 60–80% como indicio, menos se retira.

| Tipo | Convs B | % resp B | Convs A | % resp A | Precisión (n) | Estatus |
|---|---|---|---|---|---|---|
| `loop_repeticion` — Gabi repite un mensaje o pide 3× el mismo campo | 571 | 15,2% | 344 | 61,4% | 100% (10) | cifra |
| `silencio_bot` — el usuario escribe y no hay respuesta | 139 | 3,7% | 121 | 21,6% | 86% (7) | cifra |
| `nudge_anomalo` — nudge tras una respuesta real del usuario | 45 | 1,2% | 0 | — | 100% (3) | cifra |
| `intencion_ignorada` — pide humano / opt-out y Gabi sigue el guion | 9 | 0,2% | 0 | — | 100% (4) | cifra |
| `media_no_manejado` — comparte ubicación y Gabi no la acusa | 6 | 0,2% | 0 | — | 67% (6) | indicio |
| `repregunta_dato_ya_dado` — Gabi pide un dato ya entregado | 53 | 1,4% | 1 | 0,2% | 50% (12) | retirado |
| `pregunta_ignorada` — pregunta sin responder (detector estricto) | 3 | 0,1% | 2 | 0,4% | 33% (3) | retirado |
| `ambigua_registrada` — Gabi da por registrada una respuesta ambigua | 119 | 3,2% | 2 | 0,4% | 0% (12) | retirado |

Bugs técnicos (§5): `duplicado_gabi` 9 convs B, `plantilla_rota` 6 convs B + 1 A, `hora_no_monotona` 407 B / 402 A,
`latencia_alta` 36 B / 57 A (no interpretable, ver §5).

---

## 3. Detalle por tipo

### 3.1 `loop_repeticion` — Gabi se repite (571 convs B, 344 A) · precisión 10/10

Dos subtipos: **mensaje repetido** (1.330 hallazgos) y **campo pedido 3 o más veces** (100).

El caso dominante y más accionable: **493 conversaciones del bot B recibieron el mensaje de apertura
"*Recibimos tu solicitud*" dos o más veces** — 5,4% de toda la cohorte. De esas, 219 figuran como
"nunca respondió", así que el lead vio dos mensajes idénticos como primer contacto y no volvió.

```
[GABI] ¡Hola, [nombre]! *Recibimos tu solicitud* … ¿es *casa o departamento*?
[GABI] ¡Hola, [nombre]! *Recibimos tu solicitud* … ¿es *casa o departamento*?      <<< duplicado
[GABI] *Sigo pendiente de tu respuesta*
```

La variante peor es el reenvío **después** de que el usuario ya respondió (deals 1747849, 1709118, 1760235):
el usuario escribe "Departamento" y Gabi le manda otra vez la apertura, como si la conversación empezara de cero.

El subtipo `campo_repreguntado_3x` es la fricción de m² de `OPORTUNIDADES.md` §2 vista desde el otro lado:
en el deal 1705150 el usuario dice "los metros no los recuerdo" y Gabi pide el área tres veces más; en el
1705736 el usuario responde "no tengo ese dato" y Gabi insiste igual.

**Fix:** deduplicar el envío de la plantilla de apertura por `deal_id`, y cortar la re-pregunta de un campo
al segundo intento marcándolo como pendiente para el humano (es la oportunidad #4 de `OPORTUNIDADES.md`).

### 3.2 `silencio_bot` — el usuario habla y nadie contesta (139 convs B, 121 A) · precisión 6/7

195 hallazgos son "el último turno de la conversación es del usuario" y 65 son "después sólo llegó el nudge".
Se excluyen las cortesías ("ok", "gracias", 👍) y las auto-respuestas de otros negocios, porque ahí no queda
nada pendiente de responder.

Los dos casos que más cuestan:

```
[GABI] Revisando tu información … no contamos con cobertura en la zona … ¡Mucha suerte en tu venta! 🍀
[USU]  Puede hacer una oferta?                                                    <<< sin respuesta
```

```
[GABI] Solo me faltan 2 datos: 📐 *Piso* y 🚪 *Número de departamento*
[USU]  Departamento 504                                                            <<< sin respuesta
```

El segundo es el más caro: el usuario entregó el último dato del levantamiento y la conversación murió ahí.
En el bot A el fenómeno es 6 veces más frecuente (21,6% de las que responden).

**Fix:** cerrar siempre con acuse. Y revisar por qué el cierre por cobertura no acepta una réplica del usuario.

### 3.3 `nudge_anomalo` — el nudge ignora que el usuario ya contestó (45 convs B) · precisión 3/3

44 casos de nudge tras una respuesta sustantiva del usuario y 1 de dos nudges idénticos seguidos.

```
[GABI] ¿Podrías indicarnos si es *casa o departamento*…?
[USU]  Hola es casa y se encuentra en Nuevo Vallarta
[GABI] *Sigo pendiente de tu respuesta*                                            <<< nudge anómalo
```

Se concentra en las etapas tempranas: 30 de 45 mueren en *tipo* y 12 en *dirección*. **Sólo 2,2% de estas
conversaciones rutea después, contra 19,0% de las demás** — la tasa más baja de todos los tipos.

**Fix:** condicionar el nudge a que no haya mensajes del usuario posteriores al último de Gabi. Conecta con la
oportunidad #5 de `OPORTUNIDADES.md` (nudge específico en vez del genérico).

### 3.4 `intencion_ignorada` — pide un humano o dice que no (9 convs B) · precisión 4/4

6 piden hablar con un asesor, 2 son opt-out y 1 es número equivocado. Volumen chico pero cualitativamente grave:

```
[USU]  Quiero por favor hablar con un asesor
[GABI] Claro, con gusto te apoyamos 😊 En cuanto quede completa la información… Para avanzar, solo me
       faltan 2 datos: *número exterior* y *código postal*
```

```
[USU]  Escribí justamente por eso para ver cuánto me ofrecen ustedes, porque sus publicidades dicen
       "recibe una oferta en minutos", ¿es decir que su publicidad es falsa?
[GABI] Entiendo la molestia… En este momento solo me falta el *valor que pides* en *MXN*
```

Estas 9 conversaciones rutean al 44,4% (vs 18,9%): son leads con intención, atendidos mal.

**Fix:** ruta de escalamiento a humano y de baja, disparadas por intención, en vez de volver al guion.

### 3.5 `media_no_manejado` — la ubicación compartida (6 convs B) · indicio, 4/6

Sólo 6 conversaciones del trimestre compartieron una ubicación de Google/Apple Maps. En 4 Gabi la ignoró y
siguió pidiendo la dirección en texto; en 2 explicó que no puede procesar links.

**El dato relevante no es el volumen sino la asimetría:** Gabi **nunca** acepta la ubicación, ni siquiera para
pre-llenar. Compartirla es raro justamente porque el bot nunca la ofrece como opción. Esto es evidencia
directa a favor de la oportunidad #1 de `OPORTUNIDADES.md` (aceptar la ubicación de WhatsApp en la etapa de
dirección, donde mueren 1.571 conversaciones): hoy el canal existe, los usuarios lo intentan y el bot lo rechaza.

⚠ Los **adjuntos no son medibles**: fotos, audios y PDFs no dejan ningún rastro en `messages` (no hay turnos
vacíos ni marcadores). Lo único observable es la URL de maps.

### 3.6 Tipos retirados (no se reportan como cifra)

**`ambigua_registrada` (0/12).** Es el hallazgo negativo más útil del análisis: en las 12 conversaciones
revisadas, Gabi había manejado bien la ambigüedad las 12 veces — pedía aclaración ("Ese dato me quedó
*ambiguo* y no quiero registrarlo mal"), corregía, o aceptaba un aproximado. Los 119 hallazgos eran artefactos
de regex ("no **se** encuentra" leído como "no sé"; "no tengo ningún problema"). **No hay evidencia de que Gabi
registre respuestas ambiguas sin aclarar.**

**`repregunta_dato_ya_dado` (6/12).** El fenómeno existe y está bien ejemplificado (el usuario escribe
"3 recámaras" o "Precio en mxn $3,400,000" y Gabi vuelve a pedir ese campo), pero la mitad de los hallazgos son
confusiones legítimas que un humano también tendría: el área del **terreno** no es el área construida, el precio
de **compra en 2011** no es el precio pedido, "cochera" no dice cuántos cajones. **Los 6 casos confirmados están
listados en `bugs/validacion.csv`** y sirven como evidencia cualitativa; el conteo de 53 no debe citarse.

**`pregunta_ignorada` (1/3).** Tras dos iteraciones sólo sobrevive un criterio muy estricto (Gabi repite un
mensaje anterior o manda el nudge ante una pregunta con signo explícito), que deja 3 conversaciones en B. La
razón de fondo: **Gabi casi siempre responde la pregunta y además sigue el guion en el mismo mensaje**, así que
"respondió con guion" no es señal de bug. Las preguntas realmente sin respuesta aparecen bajo `silencio_bot` (§3.2).

---

## 4. Cruce con el funnel de completitud

Distribución de las conversaciones con bug por etapa de muerte del bot B (`OPORTUNIDADES.md` §1):

| Etapa de muerte | Convs | `loop_repeticion` | `silencio_bot` | `nudge_anomalo` |
|---|---|---|---|---|
| 1 nunca respondió | 5.325 | 219 | — | — |
| 2 murió en tipo | 532 | 76 | 66 | 30 |
| 3 murió en dirección | 1.571 | 123 | 11 | 12 |
| 4 murió ante el bloque | 448 | 22 | — | — |
| 5 murió en re-pregunta de m² | 140 | 18 | — | — |
| 6 completó o pasó | 1.060 | 113 | 62 | 3 |

Tres lecturas:

1. **La etapa 2 (murió en tipo) está sobre-representada en fallas del bot.** Concentra 66 de los 139 silencios y
   30 de los 45 nudges anómalos, siendo sólo el 14% de las conversaciones que responden. Una parte de esas 532
   muertes "del usuario" son en realidad muertes del bot.
2. **Las 219 aperturas duplicadas caen todas en "nunca respondió"**, la etapa que `OPORTUNIDADES.md` §3
   clasificó como la más contaminada y la más lejana a conversión. Son 219 leads (4,1% de los 5.325) donde hay
   una causa técnica identificable en vez de un lead frío.
3. **En la etapa dirección**, la fuga grande del funnel (1.571 muertes), los bugs del bot explican poco: 123 loops
   y 11 silencios. Esto refuerza la conclusión de `OPORTUNIDADES.md` §3: la fuga de dirección es fricción del
   dato pedido, no una falla del agente. El fix sigue siendo pedir menos (ubicación de WhatsApp, pre-llenado),
   no arreglar el bot.

Sobre el ruteo posterior: `nudge_anomalo` (2,2% vs 19,0%) y `pregunta_ignorada` (0% vs 18,9%) rutean mucho peor
que la base; `intencion_ignorada` (44,4%) y `repregunta_dato_ya_dado` (83,3%) mucho mejor, porque ocurren tarde
en el funnel, con leads que ya iban bien. ⚠ Es correlación con la profundidad alcanzada, no efecto causal
(mismo límite de `OPORTUNIDADES.md` §5).

---

## 5. Bugs técnicos

**Plantilla mal renderizada — 7 conversaciones.** Tres variantes reales:

| Variante | Convs | Qué se ve |
|---|---|---|
| Nombre vacío | 4 | `¡Hola, ! *Recibimos tu solicitud*` |
| NaN filtrado al nombre | 2 | `¡Hola, Nan Rea!`, `¡Hola, Nan Gutiérrez!` |
| Variable sin renderizar (bot A) | 1 | `*¿Aún te interesa vender tu inmueble en {{1}}?*` |

El "Nan" es un `NaN` de pandas convertido a texto en el pipeline de nombres. Volumen mínimo, corrección trivial,
y es el primer mensaje que ve el lead.

**Doble envío del mismo mensaje en menos de 2 minutos — 9 convs B, 2 A.** Es el mismo fenómeno del §3.1 medido
por marca de tiempo en vez de por contenido.

**Marcas de tiempo no monótonas — 407 convs B (10,9% de las que responden) y 402 A (71,8%).** Los turnos llegan
fuera de orden, con saltos hacia atrás de **7 días de mediana en B y 338 días en A**. No son minutos: son
conversaciones de varios periodos que quedan concatenadas al agregar por hora. Consecuencias:

- En el bot A la línea de tiempo es inutilizable para cualquier análisis de secuencia.
- Los cinco detectores que miran "el siguiente turno" se apagan en esas conversaciones (`es_monotona` en
  `bugs/detectores.py`). Sin ese guardarraíl, 3 de cada 5 hallazgos revisados de `pregunta_ignorada` eran este
  artefacto.

**Latencia de respuesta de Gabi: mediana 34 s y p90 42 s** sobre 9.752 pares usuario→Gabi del bot B con línea de
tiempo válida. Es sana. `latencia_alta` marca 36 conversaciones en B, pero **107 de los 121 hallazgos son de más
de un día**, o sea el mismo artefacto de multi-periodo. **La latencia no es un problema y `latencia_alta` no es
un hallazgo utilizable.**

---

## 6. Límites

- **Regex sobre texto de LLM.** La precisión de cada tipo está medida y publicada en §2; los tipos por debajo de
  60% están retirados de las cifras. Lo que **no** está medido es el *recall*: no sabemos cuántos bugs reales no
  detecta ningún patrón. Estimarlo exigiría un juez LLM sobre una muestra, que no se corrió (decisión pendiente
  de Nicolas por el envío de conversaciones a un API externo).
- **Los adjuntos no dejan rastro** en `messages`: fotos, audios y documentos son invisibles para este análisis.
  Sólo se ve la ubicación compartida como URL.
- **El orden de los turnos falla en 10,9% de B y 71,8% de A** (arriba). Los detectores de secuencia se apagan ahí,
  así que sus cifras son un **piso**, no un punto: el bug puede existir en esas conversaciones sin ser contado.
- **Correlación bug ↔ ruteo no es causal.** Quien llega más lejos ya venía más decidido (`OPORTUNIDADES.md` §5).
- **Auto-respuestas de otros negocios.** Una parte de los teléfonos no pertenece al lead sino a un comercio con
  respuesta automática ("Gracias por comunicarte con Abarrotes los Chihuahuas"). Gabi las maneja bien; se
  excluyen de los detectores, pero son una señal de calidad del dato de contacto que vale medir aparte.
- **Ventana jun–ago 2026, sólo México.** No se evaluó estacionalidad ni Colombia.

---

## 7. Reproducibilidad

```bash
cd ~/habi/tableros-marketing-habi/analisis-gabi-completitud
bq query --use_legacy_sql=false --maximum_bytes_billed=20000000000 \
  --format=json --max_rows=20000 < queries/export_conversaciones.sql > bugs/data/convs.json
bugs/.venv/bin/pytest bugs/tests -q     # 62 tests
python3 bugs/run.py                     # -> bugs/resumen.json + bugs/data/hallazgos.jsonl
python3 bugs/muestra.py <tipo> 15 7 B [compacto]   # colas redactadas para validar
python3 bugs/precision.py               # tabla de precisión de §2
```

`bugs/data/` está en `.gitignore`: las conversaciones tienen nombres, teléfonos y direcciones y **no se
commitean**. `bugs/resumen.json` (agregados sin PII) y `bugs/validacion.csv` (etiquetas sin texto) sí.
El entorno de tests es `bugs/.venv` (el Python del sistema no trae pytest y está gestionado por PEP 668).
