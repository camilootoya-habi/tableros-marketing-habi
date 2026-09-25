# Reporte diario de impacto de TV → Google Chat

Mide el tráfico incremental que genera la campaña de TV abierta en México (Televisa, sep-nov
2026) y lo publica cada mañana en un espacio de Google Chat.

Corre en **GitHub Actions** (`.github/workflows/tv-diario.yml`) con **cuatro horarios**:
**9:07, 9:31, 10:17 y 11:23 CDMX**. No depende de la máquina de nadie.

Son cuatro porque GitHub no garantiza los cron: los atrasa o los salta en horas de carga (el
25-sep el de las 9:00 no corrió). Los tres de respaldo **no duplican el mensaje**: corren con
`--solo-si-falta` y terminan sin hacer nada si `ultimo_envio.json` ya tiene esa fecha. El
marcador se escribe solo si el webhook respondió bien, así que un envío fallido se reintenta en
el siguiente horario. El workflow tiene `concurrency`, así que dos horarios atrasados nunca
corren a la vez. Una corrida manual (`workflow_dispatch`) no mira el marcador: si se lanza con
`enviar` después de que ya salió, manda otro mensaje.

## Reloj externo

GitHub **no garantiza** los cron: en horas de carga los atrasa o los descarta. El 25-sep no
corrió ninguno de los cuatro horarios, y ese día tampoco corrieron otros workflows diarios del
repo. Lo que falla es solo el disparo: un workflow lanzado por API (`workflow_dispatch`) nunca se
descarta. Por eso el disparo principal lo hace un **reloj externo gratuito** que llama a la API
de GitHub; los cuatro cron quedan de respaldo.

**Los jobs en cron-job.org** (cuenta de Nicolás; todos con `solo_si_falta`, así que después del
primer envío los demás no hacen nada):

| Hora CDMX | Para qué |
|---|---|
| 9:07 | Disparo principal |
| 9:31 | Respaldo |
| 12:07 | Reintento por si GA4 publica tarde |
| 15:07 | Reintento por si GA4 publica tarde |

cron-job.org avisa por correo si una llamada falla. Se administran por su API
(`https://api.cron-job.org`, API key en la consola → Settings) o desde su consola web.

**La llamada** (la misma en cada horario):

```
POST https://api.github.com/repos/camilootoya-habi/tableros-marketing-habi/actions/workflows/tv-diario.yml/dispatches
Authorization: Bearer <token>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28

{"ref": "main", "inputs": {"enviar": "true", "solo_si_falta": "true"}}
```

**Si GA4 todavía no publicó el día** (falta la tabla `events_AAAAMMDD` del día a reportar), la
corrida no envía ni marca, y el siguiente horario reintenta. El 25-sep el export del 24 seguía
sin llegar a las 11:50 CDMX, así que conviene que haya horarios de reintento en la tarde.

**Token actual (TEMPORAL):** clásico, de `notero-88`, scope `public_repo`, sin vencimiento.
Cambiarlo por uno fine-grained creado por Camilo (solo este repo, *Actions: Read and write*) y
revocar el clásico.

Responde **204** sin cuerpo si GitHub aceptó el disparo. `solo_si_falta` es lo que evita el
mensaje doble: si un cron de GitHub o el disparo anterior ya lo envió, esta corrida termina
sin hacer nada.

**El token:** fine-grained, creado por el **dueño del repo** (un repo personal solo admite
tokens de su dueño), con acceso **solo a `tableros-marketing-habi`** y permiso **Actions: Read
and write**, nada más. Con eso, quien lo obtenga solo puede lanzar o cancelar workflows de este
repo: no lee código privado ni hace push. Vence como máximo al año; hay que renovarlo.

**Probar la llamada** (lanza el reporte de verdad; con `solo_si_falta` no duplica):

```bash
curl -i -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/camilootoya-habi/tableros-marketing-habi/actions/workflows/tv-diario.yml/dispatches \
  -d '{"ref":"main","inputs":{"enviar":"true","solo_si_falta":"true"}}'
```

## Por qué el incremental va a 7 días y no a 24 horas

Es la decisión de diseño que más importa entender antes de tocar nada.

Un día tiene ~8 spots contra ~6.000 visitas. Se simuló el estimador diario sobre la semana 1,
donde la respuesta real se conoce por el análisis minuto a minuto (+442 visitas en la ventana
0-15 min, +514 en 0-30):

| Día (7-13 sep) | Exceso estimado |
|---|---|
| Lun | +59 |
| Mar | **−146** |
| Mié | +119 |
| Jue | **+368** |
| Vie | +212 |
| Sáb | +51 |
| Dom | **−72** |

El efecto real es de unas 65-73 visitas diarias. El estimador se mueve entre −146 y +368: el
intervalo de un día suelto es **84 ± 337**, cinco veces la señal. Publicar eso haría que un
martes cualquiera el canal dijera "−146 visitas" y alguien concluyera que la TV resta.

**Y no lo arregla tener el as-run**: con hora exacta el día mejora pero da t≈1.5, tampoco
significativo. El límite es la cantidad de spots por día, no la precisión del dato.

A 7 días rodantes, en cambio, el estimador da **t=2.06** y sostiene una lectura. Por eso la
tarjeta reporta el incremental a 7 días, y el dato de ayer lo muestra como *movimiento de
tráfico* explícitamente no atribuido a TV — que es lo único honesto que se puede decir de un
día suelto.

## Los dos estimadores

| | Unidad | Necesita | Validación semana 1 |
|---|---|---|---|
| **Banda** (`exceso_por_hora`) | hora-con-spot | solo saber **qué horas** tuvieron spot | n=52, +591 visitas, **t=2.06** |
| **Minuto** (`exceso_por_spot`) | emisión | hora exacta (as-run) | n=59, +442 visitas, **t=4.00** |

El reporte diario usa el de **banda**, porque el horario proyectado no conoce el minuto. Su
control sobre 364 horas equivalentes de semanas sin TV da media **−0.00**: es insesgado, no
inventa efecto.

Se midió además cuánta deriva de horario tolera el estimador de minuto: hasta **±15 min**
sigue significativo (t=2.02) y a ±20 se cae (t=1.65). O sea que la proyección solo tiene que
acertar la hora, no el minuto — un requisito mucho más fácil de cumplir.

## De dónde salen los spots

1. **As-run** (`spots.csv`) — lo que realmente salió al aire, con hora exacta. Llega semanal
   de la central como xlsx y `ingesta.py` lo convierte. Es la fuente de verdad.
2. **Horario proyectado** — para fechas sin as-run. Se arma con el patrón del mismo día de
   semana según el as-run más reciente.

### El xlsx NO se commitea

Este repo es **público**. El as-run de la central trae las tarifas negociadas con Televisa:
costo por spot, CPP por canal, el desglose del paquete LRDG y el tarifario completo por
programa. Eso no puede quedar en un repo que cualquiera clona.

`ingesta.py` lo parte en dos:

| | Contenido | Dónde vive |
|---|---|---|
| `spots.csv` | fecha, hora, canal, programa, franja | **Público**, se commitea |
| `inversion.json` | inversión y TRP por día × franja | **Privado**, secret `TV_INVERSION_JSON` |

Al estimador le alcanza con el calendario: solo pregunta qué horas tuvieron spot. Y que Habi
anuncie en La Rosa de Guadalupe a las 19:30 lo ve cualquiera que prenda la tele — lo sensible
es el precio, no el horario.

**Para cargar una semana nueva:**

```bash
python3 ingesta.py ~/Downloads/Tuhabi_2026_....xlsx
git add salud-marca/tv/spots.csv && git commit -m "data(tv): as-run semana NN"
```

El script imprime el JSON actualizado para pegar en el secret. El xlsx y el `inversion.json`
están en `.gitignore`, así que no hay forma de commitearlos por accidente — y un test
(`test_no_hay_xlsx_commiteado`) falla el job si alguno se cuela.

Si falta el secret, la tarjeta sale igual con el calendario y el incremental, y omite las
cifras de dinero avisándolo.

> **Límite conocido:** la proyección asume que la parrilla se repite semana a semana. Hoy hay
> un solo as-run, así que esa regularidad **no está verificada contra datos** — es un supuesto
> de negocio. `horario.regularidad()` la mide en cuanto haya dos semanas, y el reporte avisa
> en la tarjeta si baja del 70%.

## El factor del día es recortado, y por qué importa

El perfil aporta la *forma* del día; el **nivel** se estima en cada corrida con las horas sin
spot (`factor_del_dia`). Ese cálculo **recorta los extremos** en vez de promediar todo, y no
es una sutileza estadística: sin el recorte el reporte puede afirmar lo contrario de lo que
pasó.

El 22 de septiembre salió la integración de marca en *La Rosa de Guadalupe* — un paquete que
no está en el pauteo regular, así que la hora 20 no figuraba en el horario proyectado. Esa
hora se trató como "limpia", o sea como referencia de normalidad:

| | Factor del día | Exceso medido |
|---|---|---|
| Promedio simple (con el pico dentro) | 1.067 | **−60 visitas** |
| Recortado | 0.804 | **+1.934 visitas** |

El mismo día y los mismos datos, invertidos por una sola hora. El pico real fue de **15.8
sigmas**.

El recorte se validó sobre las 364 horas-con-spot equivalentes de semanas **sin** TV: media
**−0.027**, t=−0.01. Sigue insesgado.

> Nota: con el estimador recortado la semana 1 pasa de +591 a **+716 visitas** (t=2.42). No
> es un sesgo nuevo — el efecto de TV dura ~30 min y se derrama a las horas contiguas
> "limpias", inflando `k`. El recorte las descarta.

## Horas anómalas: la red para lo que el horario no contempla

`horas_anomalas()` revisa **las 24 horas**, estén o no en el horario, y marca las que superan
**4 sigmas** sobre su propia dispersión histórica. Por eso `baseline.json` guarda media y
desviación por (día de semana, hora), no solo el perfil por minuto.

El umbral es 4 y no 2 a propósito: con 24 horas diarias, a 2 sigmas habría un falso positivo
casi todos los días.

Cuando la anomalía cae **fuera** del horario de spots, la tarjeta lo dice explícitamente —
esas horas no entran en el incremental de 7 días y hay que revisar si salió algo no previsto
en el plan.

## El baseline está congelado a propósito

`baseline.json` es el perfil minuto a minuto del tráfico **sin** televisión, calculado sobre
el 20-jul → 6-sep 2026 (siete semanas Lun-Dom previas a la campaña).

Si se recalculara con datos recientes iría absorbiendo el propio efecto de la campaña: cada
semana el "normal" subiría un poco y el incremental medido bajaría hasta desaparecer. Un
contrafactual tiene que venir de un período donde el tratamiento no existía.

Además del perfil por minuto, guarda media y desviación por (día de semana, hora), que es lo
que permite calificar una hora como anómala.

Regenerar solo si la campaña se extiende más allá de 2026 o si el sitio cambia
estructuralmente: `python3 salud-marca/tv/baseline.py`

## El panel del tablero de salud de marca

Cada corrida escribe también `metrics.tv` en `salud-marca/data.json`, que alimenta dos
gráficas del tablero:

| Gráfica | Qué muestra | Cómo leerla |
|---|---|---|
| **Diaria** | Observado vs contrafactual desde el 31-ago | **Descriptiva.** La brecha incluye pauta digital, feriados y estacionalidad — no es incrementalidad de TV |
| **Intradía** | El último día cerrado, sumado en bloques de 10 min (o 30, con un botón), con el contrafactual reescalado al nivel del día y una línea ámbar por spot | Aquí **sí** se aísla una emisión: el 22-sep el minuto 20:08 tuvo 206 visitas contra 5.7 esperadas. Se suma en bloques porque por minuto llegan ~7 visitas y el ruido de conteo (±3) hacía parecer que la serie estaba siempre por encima del contrafactual |

Los días con alguna hora anómala salen con punto rojo en la serie diaria.

### Leads diarios

`metrics.tv.MX.leads` compara los leads WEB de México (`tabla_inmuebles_general`,
`fuente_id=3`) contra un contrafactual por día de semana. Se parten en tres series porque
no todas responden igual a una emisión:

| Serie | Qué es | Por qué |
|---|---|---|
| **Directo** (default) | Sin UTM | URL escrita u orgánico: lo que la TV puede mover sin pasar por ningún anuncio |
| **Búsqueda de marca** | Google Ads `sem_brand` | Alguien buscó "habi". También depende del presupuesto de esas campañas |
| **Todos WEB** | Todo `fuente_id=3` | Contexto. La mayoría es pauta de Meta/Google |

El contrafactual es la **mediana** de cada día de semana del 20-jul al 6-sep, no el promedio:
el 17-30 ago la pauta digital infló los leads WEB (~+60/día, casi todo con UTM de Facebook y
Google) y con el promedio cualquier semana de campaña parecería caer. El tablero dice cuánto
se mueve un día normal (`ruido`) y avisa si la serie ya subía la semana previa al primer spot.

Es descriptivo, como el tráfico diario. Primera lectura (7-23 sep): +62 leads directos, pero
+96 son del **22-sep** (integración en *La Rosa de Guadalupe*); el resto de los días queda
dentro del ruido.

Solo se guarda **un día** de minuto a minuto (~25 KB, 1.440 puntos). Una semana metería
~10.000 puntos en un `data.json` que el navegador descarga entero antes de pintar.

`inyectar()` reescribe **solo** la clave `tv` y deja el resto intacto: las otras métricas
vienen de `build.py`, que corre a mano, y un rewrite completo desde el cron borraría el caché
histórico de Brand Lift.

## Configuración

Dos secrets del repo:

- `GCP_CREDENTIALS` — ya existe, lo comparte con `update-data.yml`.
- `TV_INVERSION_JSON` — **falta crearlo**. Lo imprime `ingesta.py`. Sin él el reporte
  funciona, solo omite inversión y TRP.
- `GCHAT_WEBHOOK_TV` — **falta crearlo**. En el espacio de Google Chat: *Apps e integraciones
  → Webhooks → Agregar webhook*. La URL que devuelve **es la credencial completa**; va solo
  en el secret. Los webhooks funcionan en espacios, no en mensajes directos, y algunos
  Workspace los tienen bloqueados por política.

## Uso local

```bash
python3 reporte_diario.py                      # calcula e imprime, NO envía
python3 reporte_diario.py --fecha 2026-09-13   # un día específico
python3 reporte_diario.py --enviar             # además postea
python3 -m pytest tests/ -q
```

Requiere `bq` autenticado y `openpyxl`.

## Archivos

| | |
|---|---|
| `estimador.py` | la matemática. Funciones puras, sin BigQuery ni red |
| `ingesta.py` | convierte el xlsx de la central en `spots.csv` + `inversion.json` |
| `horario.py` | lee el as-run y proyecta el horario de las fechas que no lo tienen |
| `baseline.py` | construye y carga el contrafactual congelado |
| `chat.py` | arma la tarjeta y la postea al webhook |
| `reporte_diario.py` | orquesta y es el entrypoint del workflow |

## Pendientes

- **Pedir el as-run diario a la central.** El monitoreo se genera diario; hoy lo mandan
  semanal. El día que llegue diario, el reporte pasa a ser definitivo sin tocar código.
- **Leads incrementales.** La señal existe pero no cruza significancia con una semana (+16
  leads en 0-5 min, t=1.66). Con 4-5 semanas probablemente sí, y ahí vale agregarla.
- **Corrección de los lunes.** Hoy el recálculo con as-run ocurre solo, al reingerir el
  archivo. Falta que la tarjeta del lunes diga explícitamente qué cifras cambiaron.
