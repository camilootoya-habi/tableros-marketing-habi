# Reporte diario de impacto de TV → Google Chat

Mide el tráfico incremental que genera la campaña de TV abierta en México (Televisa, sep-nov
2026) y lo publica cada mañana en un espacio de Google Chat.

Corre en **GitHub Actions** (`.github/workflows/tv-diario.yml`), a las **15:00 UTC = 09:00
CDMX**. No depende de la máquina de nadie.

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

## El baseline está congelado a propósito

`baseline.json` es el perfil minuto a minuto del tráfico **sin** televisión, calculado sobre
el 20-jul → 6-sep 2026 (siete semanas Lun-Dom previas a la campaña).

Si se recalculara con datos recientes iría absorbiendo el propio efecto de la campaña: cada
semana el "normal" subiría un poco y el incremental medido bajaría hasta desaparecer. Un
contrafactual tiene que venir de un período donde el tratamiento no existía.

Lo que sí se ajusta en cada corrida es el **nivel** del día (`factor_del_dia`), estimado con
las horas sin spot de ese mismo día. Así el perfil aporta la *forma* y el día su *altura*, y
un cambio de nivel — más pauta digital, un feriado — no se lee como efecto de TV.

Regenerar solo si la campaña se extiende más allá de 2026 o si el sitio cambia
estructuralmente: `python3 salud-marca/tv/baseline.py`

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
