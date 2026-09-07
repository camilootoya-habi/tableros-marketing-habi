# Ventanas · tabla de control, gráficas y salud del agente — diseño

Fecha: 2026-09-07 · Tablero: `marketing-loop/` (panel, canal **Ventanas**, país CO) · Estado: borrador para revisión.

## 1. Objetivo

Detectar en un vistazo cuándo el programa Ventanas se apaga o se degrada, y en qué tramo:
entrada (HubSpot), salida (nuestros envíos), embudo por cohorte o salud del agente. Hoy el
panel de Ventanas tiene tres cards (Embudo de Ventanas, Desenlace de los leads de HubSpot,
Entrevista). Lo nuevo va **debajo de esas tres**, en este orden: selector de ruta → tabla de
control (bloques 1, 2 y 3) → franja de salud del agente (bloque 4) → gráfica de volumen →
gráfica de calidad.

## 2. Decisiones ya tomadas

| Tema | Decisión |
|---|---|
| Ruta | Por **flujo primero y kind después**, por teléfono, con su primer POST (§3.2). Tres rutas: `compra_directa`, `tibio`, `nocontesta`. |
| Frescura | **Híbrido.** Todo sale del `data.json` diario (build 9:30). El bloque 1 de HOY y el bloque 4 se refrescan en vivo desde un endpoint nuevo del agente en Vercel, con test de contrato. |
| Layout | **Selector de ruta arriba** (Todas · Compra directa · Tibio · No contesta). Una columna por métrica. Las gráficas muestran las tres rutas como series siempre. |

## 3. Definiciones comunes

### 3.1 Tiempo
- Día = calendario de `America/Bogota`.
- Día hábil = lunes a viernes. (Sin festivos: no hay calendario en el sistema; se documenta.)
- Cohorte **madura** = han pasado **4 días calendario o más** desde el día de la cohorte. Cubre el reloj de 72 h que dispara el deal parcial y el handoff.
- Semana = ISO, lunes a domingo, para las columnas semanales (Entregados, Estado de plantillas).

### 3.2 Ruta (por teléfono, con su primer POST no `DRY:`)
```
CASE
  WHEN flujo = 'compra_wa'                                   THEN 'compra_directa'
  WHEN kind = 'whatsapp' OR gestion ILIKE '%whatsapp%'       THEN 'tibio'
  ELSE                                                            'nocontesta'
END
```
`kind` es la clasificación ya guardada de la gestión (classify). El `ILIKE` cubre las filas de
recuperación que traen `kind` vacío. Un teléfono tiene **una** ruta: la de su primer POST.
Verificado el 7-sep: 265 compra_directa (plantilla `ventanas_compra_co_v1`), 61 tibio
(`ventanas_tibio_co_v1`), 652 nocontesta (`ventanas_nocontesta_co_v1`).

### 3.3 Exclusiones
- `action LIKE 'DRY:%'` se excluye **siempre** (pruebas en seco).
- `action LIKE 'RECUPERADO_%'` (tandas manuales del 26, 28 y 31-ago, 441 filas) se excluye del
  **bloque 1** porque no son POSTs del workflow de HubSpot y el bloque 1 mide a HubSpot. **Sí**
  cuentan para asignar cohorte y ruta en el bloque 3: esa gente entró al pipeline ese día.
  El tooltip de "POSTs recibidos" lo dice.

### 3.4 Semáforo
- **Referencia** (fila al pie): mediana de los **últimos 7 días hábiles maduros** de cada
  columna, por ruta seleccionada. Se calcula en el build, no en el navegador.
- **Rojo por caída**: celda **< 30 %** de su referencia. Aplica solo a columnas de volumen y de
  conversión: filas 1, 2, 3, 7, 11, 12, 13, 14, 19. Si la referencia es 0 no se pinta.
- **Rojo por falla** (>0): SIN_DIRECCION, NO_TEMPLATE, SEND_FAIL, BAD_PHONE (fila 5), Rechazos
  de Infobip (9), Deal falló (16), Errores del agente (24), Plantilla no APPROVED (25).
- **Gris** (guarda, informativo): TERMINAL, CAP_DIARIO, FUERA_HORARIO, DEDUP.
- **Rojo por silencio** (fila 6): día hábil sin ningún POST; y para HOY, además, si son las
  10:00 o más y no hay POST. Esta segunda condición solo se evalúa con el dato en vivo (§6).
- **Opt-out** (18): rojo si supera el 5 % de "Respondieron" de la misma cohorte.

## 4. Métricas (fuente y cálculo exactos)

Todo por ruta; "Todas" es la suma de las tres (o la mediana global en la fila de referencia).

### Bloque 1 · Entrada (por día de recepción, tabla `ventanas_hs_inbound`, sin DRY ni RECUPERADO)
| # | Métrica | Cálculo |
|---|---|---|
| 1 | POSTs recibidos | filas del día |
| 2 | Personas recibidas | `count(DISTINCT phone)` del día |
| 3 | Personas nuevas | teléfonos cuyo primer POST de la historia es ese día |
| 4 | Tasa de DEDUP | filas `action='DEDUP'` ÷ POSTs del día |
| 5 | Bloqueos | conteo por `action` ∉ {SENT, DEDUP}; guardas en gris, fallas en rojo (§3.4). Tooltip: desglose por action |
| 6 | Hora del último POST | `max(received_at)` del día, hora Bogotá |

### Bloque 2 · Salida (por día de envío, tabla `send_log`, `template LIKE 'ventanas%'`)
| # | Métrica | Cálculo |
|---|---|---|
| 7 | Primer envío | `accepted` y template ∈ {`ventanas_nocontesta_co_v1`, `ventanas_compra_co_v1`, `ventanas_tibio_co_v1`}. Tibio es el **primer** envío de su ruta. Debe cuadrar con SENT del bloque 1; el tooltip muestra la diferencia |
| 8 | Seguimientos | `accepted` y template = `ventanas_reenganche_co_v1` (único seguimiento) |
| 9 | Rechazos de Infobip | `accepted = false` |
| 10 | Entregados (semanal) | message_ids del primer envío de la semana con estado *delivered* en el mart de BigQuery (`mart_by_msgid`, CO). Columna por semana ISO, últimas 6 |

La ruta de un envío es la ruta del teléfono (§3.2).

### Bloque 3 · Embudo por cohorte (fila = día del primer POST del teléfono, incluye RECUPERADO)
| # | Métrica | Cálculo |
|---|---|---|
| 11 | Respondieron | teléfonos de la cohorte con turno `role='user'` y `campaign='ventanas'` en `agent_thread` **∪** con `responded_at` no nulo en `contact_status`. La unión es obligatoria: los clics de botón no llegan al agente |
| 12 | Consintieron | `ventanas_intake.consent = true`. % sobre 11 |
| 13 | Entrevista completa | `completed_at IS NOT NULL AND step IS NULL`. % sobre 12 |
| 14 | Deal completo | `ventanas_backbone_intento.resultado='BACKBONE'` y el intake con `step IS NULL`. Un teléfono cuenta una vez |
| 15 | Deal parcial | `resultado='BACKBONE'` y el intake con `step IS NOT NULL` (los del reloj de 72 h). Columna aparte, nunca sumada a 14 |
| 16 | Deal falló | `resultado='BACKBONE_FAILED'`. Rojo siempre; `http_code`s en el tooltip |
| 17 | Handoff a Dapta | teléfonos en `ventanas_dapta_handoff`, dos sub-columnas: `SIN_RESPUESTA_24H` (salida normal) y `PIDE_LLAMADA` (intención positiva) |
| 18 | Opt-out | teléfonos con `action_taken='CLOSE_OPT_OUT'` en `agent_thread`. Rojo si > 5 % de 11 |
| 19 | Conversión total | 14 ÷ 3 (deal completo sobre personas nuevas). Solo cohortes maduras; en inmaduras la celda dice "·" |
| 20 | Horas a deal | mediana de `lead_fired_at − primer POST`, en horas, por cohorte |

Cada columna 11–14 lleva debajo, en pequeño, el % sobre la columna anterior.

### Bloque 4 · Salud del agente (por día de actividad)
| # | Métrica | Cálculo |
|---|---|---|
| 21 | Entrevistas atascadas | teléfonos donde el asistente (`role='assistant'`, `campaign='ventanas'`) repitió **el mismo texto 3 o más veces seguidas** en el día |
| 22 | Entrevistas abiertas | `consent` y `step IS NOT NULL` y `last_inbound_at` en las últimas 72 h y `lead_fired_at IS NULL` |
| 23 | Latencia de respuesta | mediana de `ts` del turno assistant − `ts` del turno user inmediatamente anterior, por teléfono. Rojo si > 60 s |
| 24 | Errores del agente | turnos con `action_taken IN ('TURN_ERROR','LLM_ERROR')`. Rojo si > 0 |
| 25 | Estado de plantillas (semanal) | por plantilla `ventanas%`: APPROVED o no. Sale del catálogo de Infobip que el build ya trae en `plantillas` |

## 5. Arquitectura

### 5.1 Build diario (este repo)
Módulo nuevo `marketing-loop/ventanas_control.py`, llamado desde `build_data.py`. Separa en
dos capas para que se pueda probar sin base:
- **Extracción**: una función por tabla que devuelve filas crudas de Neon (vía `sources_neon._rows`).
  Sin lógica.
- **Agregación pura**: funciones que reciben listas de dicts y devuelven el JSON. Aquí vive
  la regla de ruta, la asignación de cohorte, la madurez, la mediana de referencia y el
  semáforo. **Con tests** (`tests/test_ventanas_control.py`) sobre fixtures pequeñas.

Salida en `data.json` bajo `ventanas.control`:
```
{ "generado": "2026-09-07T14:48Z",
  "rutas": ["compra_directa","tibio","nocontesta"],
  "dias": [ { "fecha": "2026-09-04", "habil": true, "madura": false,
              "todas": {B1, B2, B3}, "compra_directa": {...}, "tibio": {...}, "nocontesta": {...} } ],
  "semanas": [ { "semana": "2026-W36", "todas": {"primer_envio", "entregados"}, "<ruta>": {...} } ],
  "agente": [ { "fecha", "atascadas", "abiertas", "latencia_s", "errores" } ],
  "plantillas": [ { "nombre", "estado", "aprobada": true } ],
  "referencia": { "todas": {"posts": 180, ...}, "<ruta>": {...} } }
```
donde B1 = `{posts, personas, nuevas, dedup_pct, bloqueos:{action:n}, ultimo_post:"HH:MM"}`,
B2 = `{primer_envio, seguimientos, rechazos}`,
B3 = `{respondieron, consintieron, entrevista_completa, deal_completo, deal_parcial, deal_fallo, deal_fallo_codes:[..], handoff_sin_respuesta, handoff_pide_llamada, optout, conversion_total, horas_a_deal}`.
`dias` trae los últimos **20 días hábiles** más hoy y los fines de semana intermedios (marcados
`habil:false`, se muestran atenuados para que el eje de fechas no mienta).

### 5.2 Endpoint en vivo (repo marketing-loop-sellers, rama del agente)
`GET /api/ventanas/control-hoy?token=<INBOX_TOKEN>` en `plantillas/envio.py`, junto a
`/api/ventanas/alertas`, misma autenticación y CORS. Devuelve:
```
{ "fecha": "2026-09-07", "hora": "10:07",
  "b1": { "todas": B1, "compra_directa": B1, "tibio": B1, "nocontesta": B1 },
  "agente": { "atascadas", "abiertas", "latencia_s", "errores" } }
```
Solo HOY del bloque 1 y el bloque 4: es lo único que necesita frescura. Se agrega al contrato
en `tests/test_tablero_contract.py` de aquel repo. La SQL del bloque 1 y del bloque 4 queda
duplicada entre los dos repos a propósito (repos distintos); el contrato fija los nombres de
campo y los dos commits se referencian.

### 5.3 Tablero (`marketing-loop/index.html`)
`renderVentanasControl()` se llama desde `renderVentanasPanel()` después de las tres cards.
Pinta desde `D.ventanas.control`. Si hay token guardado, hace `fetch` al endpoint y **sobre-
escribe** la fila de hoy del bloque 1 y la franja del bloque 4, marcando "en vivo HH:MM"; sin
token o con error, muestra el dato del build con su hora y no falla. Selector de ruta como
control segmentado (`.seg .winbtn.sm`, igual al de rango del embudo). Toda métrica lleva la
"i" con hover (`MET_HELP`) con el texto de la columna Cálculo de §4.

### 5.4 Piezas visuales
- **Tabla de control**: una fila por día (más reciente arriba), grupos de columnas B1 · B2 · B3
  con cabecera de grupo; fila de referencia fija al pie; scroll horizontal dentro de la card.
  Las columnas semanales (10, 25) no van en esta tabla: van en una mini-tabla "Semanal" a la
  derecha de la franja del bloque 4.
- **Franja bloque 4**: 5 celdas tipo KPI (21–25), con el semáforo de §3.4.
- **Gráfica de volumen** (Chart.js): barras **apiladas** de personas nuevas por día, una serie
  por ruta, colores fijos por ruta validados en claro y oscuro. Fines de semana atenuados.
- **Gráfica de calidad**: líneas de conversión total (fila 19) por cohorte **madura**, una por
  ruta, eje en %; cohortes inmaduras no se dibujan. Un solo eje.

## 6. Manejo de errores y límites
- Neon caído en el build: `ventanas.control` sale con `"error"` y el tablero muestra la card
  con el mensaje y la hora del último dato bueno (no rompe el resto del panel).
- Endpoint en vivo caído: se muestra el dato del build; nunca se oculta la tabla.
- La regla "10 am sin POST" solo puede evaluarse con el dato en vivo; con el del build se
  muestra la hora que había a las 9:30 sin pintar rojo por esa regla.
- Cohortes con menos de 5 personas nuevas: se muestran, pero su % no entra a la referencia.

## 7. Pruebas
- Python: `tests/test_ventanas_control.py` con fixtures de 10–20 filas: ruta (los 3 casos +
  kind vacío con gestión WhatsApp), cohorte y madurez, unión de "Respondieron", deal completo
  vs parcial, mediana de referencia con fines de semana intermedios, semáforo (<30 %, fallas,
  silencio, opt-out 5 %).
- Contrato: test nuevo en marketing-loop-sellers para `/api/ventanas/control-hoy`.
- Visual: captura headless en claro y oscuro, pestaña Ventanas, antes del commit.

## 8. Fuera de alcance
México (Ventanas es solo CO). Alertas push. Festivos colombianos. Cambiar las tres cards
existentes de Ventanas.
