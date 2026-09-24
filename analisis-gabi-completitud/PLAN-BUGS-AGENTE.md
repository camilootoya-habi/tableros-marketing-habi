# Detección de bugs y fallas del agente Gabi (MX) — Plan de análisis

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recorrer TODAS las conversaciones de Gabi (bots A y B, jun–ago 2026) y cuantificar, con detectores reproducibles y validación manual, las fallas del agente: preguntas del usuario que quedaron sin respuesta, respuestas ambiguas que Gabi "registró" sin aclarar, datos ya entregados que vuelve a pedir, silencios, nudges mal disparados, loops, plantillas rotas e intenciones (opt-out, "quiero un asesor") ignoradas.

**Architecture:** Una sola pasada de BigQuery exporta las conversaciones a un JSON local **no versionado** (tiene PII). Un parser en Python las convierte en turnos `(rol, texto, hora)`; una batería de detectores (funciones puras, con tests) etiqueta hallazgos por conversación; un runner agrega por bot × tipo × etapa de muerte × ruteo y escribe un `resumen.json` sin PII. Cada detector se valida a mano con una muestra (precisión ≥ 80% o se degrada a "indicio"). Las dos categorías semánticas (pregunta sin respuesta, ambigüedad ignorada) se refuerzan con un juez LLM opcional sobre una muestra redactada. El entregable es `BUGS-AGENTE.md` con la tabla de fallas, ejemplos redactados y el cruce con el funnel de `OPORTUNIDADES.md`.

**Tech Stack:** `bq` CLI (solo lecturas, `--maximum_bytes_billed=20000000000`), Python 3 estándar (`re`, `json`, `datetime`, `statistics`), `pytest`, opcional `anthropic` SDK para el juez.

**Contexto previo obligatorio:** leer `PROMPT-SESION.md` y `OPORTUNIDADES.md` de esta carpeta. Los marcadores de etapa y el patrón de dedup (`QUALIFY last_execution_timestamp = MAX(...)` + `STRING_AGG ... ORDER BY HORA`) se **reutilizan verbatim** de `queries/muerte_por_etapa_desenlace.sql` y `queries/funnel_etapas_botA.sql`; no se re-derivan.

**Rama:** `pool-ab-view` (la de trabajo del análisis). Commit + push tras cada tarea; si el push es rechazado, `git pull --rebase` y reintentar (un workflow pushea `data.json` solo).

---

## Taxonomía de fallas (qué vamos a buscar)

| # | Tipo (`tipo` en el JSONL) | Qué es | Señal en la conversación | Nivel |
|---|---|---|---|---|
| 1 | `pregunta_ignorada` | El usuario preguntó algo y Gabi no lo contestó | Turno de usuario con `?`/`¿`/interrogativo → el siguiente turno de Gabi es un mensaje de guion (bot B) o el nudge, o no hay siguiente turno | contenido |
| 2 | `ambigua_registrada` | El usuario respondió ambiguo/incompleto y Gabi dijo "Ya anoté" sin aclarar | Usuario con `no sé / aprox / más o menos / creo / depende` o sin dígitos donde se esperaba número → Gabi responde con acuse (`Perfecto / Ya anoté / Ya registré`) sin re-preguntar ese dato | contenido |
| 3 | `repregunta_dato_ya_dado` | Gabi pide un dato que el usuario ya había escrito | Usuario escribió `120 m2` / `$2,500,000` / `3 recámaras` y luego Gabi dice "Solo me falta … *área construida* / *valor*" | contenido |
| 4 | `intencion_ignorada` | El usuario dijo "ya vendí / no me interesa / quiero hablar con un asesor / cuánto me ofrecen" y Gabi siguió el guion | Usuario con patrón de opt-out o de pedido a humano → Gabi responde con guion o nudge | contenido |
| 5 | `media_no_manejado` | El usuario mandó imagen/audio/ubicación/URL de mapa y Gabi siguió pidiendo texto | Turno de usuario vacío o con marcador de adjunto/URL → Gabi responde con guion | contenido |
| 6 | `silencio_bot` | El usuario escribió y Gabi nunca contestó (o solo el nudge horas después) | Último turno es del usuario; o usuario → nudge sin ningún mensaje de guion entre medio | estructural |
| 7 | `nudge_anomalo` | "Sigo pendiente de tu respuesta" disparado justo después de que el usuario SÍ respondió, o dos nudges seguidos | Nudge cuyo turno anterior es del usuario; nudge → nudge | estructural |
| 8 | `loop_repeticion` | Gabi repite exactamente el mismo mensaje (no nudge) ≥ 2 veces, o pide el mismo campo ≥ 3 veces | Textos de Gabi normalizados iguales; `falta … <campo>` × 3 | estructural |
| 9 | `duplicado_gabi` | Dos mensajes de Gabi idénticos con < 2 min de diferencia (doble envío) | Turnos consecutivos de Gabi, mismo texto, Δt < 120 s | técnico |
| 10 | `plantilla_rota` | Variables sin renderizar o valores nulos en el texto de Gabi | `None`, `null`, `nan`, `{nombre}`, `{{`, `¡Hola, !` | técnico |
| 11 | `hora_no_monotona` | Turnos fuera de orden temporal (posible artefacto de la agregación por hora) | `hora[i] < hora[i-1]` | dato |
| 12 | `latencia_alta` | Respuesta de Gabi (no nudge) > 10 min después del usuario | Δt usuario → Gabi > 600 s | técnico |

Los tipos 1–5 son "el agente entendió mal"; 6–9 son "el agente no respondió o respondió de más"; 10–12 son calidad técnica/dato. Los niveles **contenido** requieren validación manual obligatoria (Task 6) porque son regex sobre lenguaje natural.

---

## File Structure

Todo dentro de `analisis-gabi-completitud/` (regla de la sesión: no tocar nada fuera).

- Create: `bugs/.gitignore` — ignora `data/` (las conversaciones exportadas tienen nombres, teléfonos y direcciones: **nunca se commitean**).
- Create: `queries/export_conversaciones.sql` — una pasada de `mabi_mx` (≈2,4 GB) que devuelve 1 fila por deal con `bot`, `etapa_muerte`, `agendo`, `inmo` y la conversación `c`.
- Create: `bugs/parse.py` — `parse_turns(c) -> list[Turn]`, `redact(texto)`, `is_nudge(texto)`. Una responsabilidad: convertir texto crudo en turnos.
- Create: `bugs/detectores.py` — constantes regex + una función `det_<tipo>(turns, bot) -> list[dict]` por tipo + `TODOS` (lista de detectores).
- Create: `bugs/run.py` — carga `bugs/data/convs.json`, corre detectores, escribe `bugs/data/hallazgos.jsonl` (con PII, ignorado) y `bugs/resumen.json` (agregados, commiteable).
- Create: `bugs/muestra.py` — imprime N conversaciones redactadas de un tipo para validación manual.
- Create: `bugs/precision.py` — lee `bugs/validacion.csv` y calcula precisión por tipo.
- Create: `bugs/juez.py` — (opcional) juez LLM sobre una muestra redactada.
- Create: `bugs/tests/conftest.py`, `bugs/tests/test_parse.py`, `bugs/tests/test_detectores.py`, `bugs/tests/test_run.py`.
- Create: `bugs/validacion.csv` — etiquetas manuales (solo `deal_id`, sin texto).
- Create: `BUGS-AGENTE.md` — el informe.
- Modify: `PROMPT-SESION.md` — agregar el hilo "bugs del agente" a HILOS ABIERTOS con puntero al informe.

Comandos de test siempre desde la carpeta del análisis:

```bash
cd ~/habi/tableros-marketing-habi/analisis-gabi-completitud
bugs/.venv/bin/pytest bugs/tests -q
```

---

### Task 0: Preparación de la carpeta `bugs/`

**Files:**
- Create: `bugs/.gitignore`
- Create: `bugs/tests/conftest.py`

- [ ] **Step 1: Sincronizar la rama**

```bash
cd ~/habi/tableros-marketing-habi && git checkout pool-ab-view && git pull --ff-only
```
Expected: `Already up to date.` o un fast-forward limpio.

- [ ] **Step 2: Crear la estructura y el .gitignore**

```bash
cd ~/habi/tableros-marketing-habi/analisis-gabi-completitud
mkdir -p bugs/data bugs/tests
printf 'data/\n__pycache__/\n' > bugs/.gitignore
```

- [ ] **Step 3: conftest para que los tests importen los módulos de `bugs/`**

`bugs/tests/conftest.py`:
```python
import sys
from pathlib import Path

# Permite `from parse import ...` y `from detectores import ...` desde los tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

- [ ] **Step 4: Verificar que pytest arranca vacío**

```bash
bugs/.venv/bin/pytest bugs/tests -q
```
Expected: `no tests ran` (exit code 5). Es lo esperado.

- [ ] **Step 5: Commit**

```bash
git add bugs/.gitignore bugs/tests/conftest.py
git commit -m "analisis(gabi): esqueleto de bugs/ para deteccion de fallas del agente (data/ ignorado)"
```

---

### Task 1: Exportar las conversaciones (una pasada de BigQuery)

**Files:**
- Create: `queries/export_conversaciones.sql`
- Genera (ignorado): `bugs/data/convs.json`

- [ ] **Step 1: Escribir la query**

Reutiliza verbatim los CTEs `ult`/`conv`/`g`/`gi` y los `CASE` de etapa de `queries/muerte_por_etapa_desenlace.sql` (bot B) y `queries/funnel_etapas_botA.sql` (bot A). Filtra el bot A por fecha real del último mensaje, como manda `PROMPT-SESION.md`.

`queries/export_conversaciones.sql`:
```sql
-- Export de conversaciones de Gabi (bots A y B, jun-ago 2026) para la detección de bugs del agente.
-- 1 fila = 1 deal_id (última ejecución; mensajes agregados por HORA). ~2,4 GB por pasada.
-- El resultado tiene PII (nombres, teléfonos, direcciones): se guarda en bugs/data/ (gitignored).
WITH ult AS (
  SELECT deal_id, nid, messages, last_activity, last_execution_timestamp
  FROM `sellers-main-prod.chatbots.mabi_mx`
  WHERE last_activity BETWEEN DATETIME '2026-06-01' AND DATETIME '2026-08-31 23:59:59'
  QUALIFY last_execution_timestamp = MAX(last_execution_timestamp) OVER (PARTITION BY deal_id)
),
conv AS (
  SELECT deal_id, ANY_VALUE(nid) AS nid, MAX(last_activity) AS la,
    STRING_AGG(messages, '\n' ORDER BY REGEXP_EXTRACT(messages, r'HORA: ([0-9T:.\-]+)')) AS c
  FROM ult GROUP BY 1
),
g  AS (SELECT DISTINCT deal_id FROM `sellers-main-prod.chatbots.gabi_mx`),
gi AS (SELECT DISTINCT nid FROM `sellers-main-prod.chatbots.gabi_inmo_mx` WHERE nid IS NOT NULL),
f AS (
  SELECT conv.deal_id, la, c,
    CASE
      WHEN REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Recibimos tu solicitud')   THEN 'B'
      WHEN REGEXP_CONTAINS(REGEXP_EXTRACT(c, r'(?m)^Gabi: ([^\n]{0,200})'), r'Has solicitado una Oferta') THEN 'A'
      ELSE 'OTRO' END AS bot,
    SUBSTR((SELECT MAX(h) FROM UNNEST(REGEXP_EXTRACT_ALL(c, r'HORA: ([0-9T:.\-]+)')) h), 1, 7) AS ult_mes_real,
    IF(g.deal_id IS NULL, 0, 1) AS agendo,
    IF(gi.nid   IS NULL, 0, 1)  AS inmo
  FROM conv
  LEFT JOIN g  ON conv.deal_id = g.deal_id
  LEFT JOIN gi ON conv.nid = gi.nid
)
SELECT deal_id, bot, DATE(la) AS last_activity, agendo, inmo,
  CASE
    WHEN bot = 'B' THEN
      CASE
        WHEN ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) = 0 THEN '1_nunca_respondio'
        WHEN NOT REGEXP_CONTAINS(c, r'(?i)\*direcci[óo]n\*') THEN '2_murio_en_tipo'
        WHEN NOT REGEXP_CONTAINS(c, r'(?i)\*antig[üu]edad\*') THEN '3_murio_en_direccion'
        WHEN NOT REGEXP_CONTAINS(IFNULL(REGEXP_EXTRACT(c, r'(?si)\*antig[üu]edad\*(.*)$'), ''), r'Usuario:') THEN '4_murio_ante_bloque'
        WHEN REGEXP_CONTAINS(c, r'(?i)falta[\s\S]{0,200}?[áa]rea construida')
             AND NOT REGEXP_CONTAINS(
               IFNULL(REGEXP_EXTRACT(c, r'(?si)^.*falta[\s\S]{0,200}?[áa]rea construida(.*)$'), 'Usuario:'),
               r'Usuario:') THEN '5_murio_en_reask_m2'
        ELSE '6_completo_o_paso' END
    ELSE
      CASE
        WHEN ARRAY_LENGTH(REGEXP_EXTRACT_ALL(c, r'(?m)^Usuario:')) = 0 THEN '1_nunca_respondio'
        WHEN NOT REGEXP_CONTAINS(c, r'(?mi)^Gabi:[^\n]*direcci[óo]n') THEN '2_murio_en_consentimiento'
        WHEN NOT REGEXP_CONTAINS(c, r'(?i)antig[üu]edad') THEN '3_murio_en_direccion'
        WHEN NOT REGEXP_CONTAINS(c, r'(?mi)^Gabi:[^\n]*(casa sola|departamento en condominio|edificio solo|metros cuadrados|m²)') THEN '4_murio_en_antiguedad_precio'
        WHEN NOT REGEXP_CONTAINS(c, r'(?i)ba[ñn]os completos|cu[áa]ntos ba[ñn]os') THEN '5_murio_en_tipo_m2_recamaras'
        WHEN NOT REGEXP_CONTAINS(c, r'(?i)tengo toda la informaci[óo]n|Terminamos de analizar tu solicitud') THEN '6_murio_en_banos_estac'
        ELSE '7_completo' END
  END AS etapa_muerte,
  c
FROM f
WHERE bot = 'B'
   OR (bot = 'A' AND ult_mes_real IN ('2026-06', '2026-07', '2026-08'))
```

- [ ] **Step 2: Correr la query y guardar el JSON**

```bash
cd ~/habi/tableros-marketing-habi/analisis-gabi-completitud
bq query --use_legacy_sql=false --maximum_bytes_billed=20000000000 \
  --format=json --max_rows=20000 < queries/export_conversaciones.sql > bugs/data/convs.json
```
`bq` imprime los errores por STDOUT con rc=1 y stderr vacío: si el archivo no es JSON válido en el paso 3, abrirlo y leer el error.

- [ ] **Step 3: Verificar el export contra las cifras conocidas**

```bash
python3 - <<'EOF'
import json, collections
rows = json.load(open('bugs/data/convs.json'))
print('deals:', len(rows))
print('por bot:', collections.Counter(r['bot'] for r in rows))
print('etapas B:', sorted(collections.Counter(r['etapa_muerte'] for r in rows if r['bot']=='B').items()))
print('sin texto:', sum(1 for r in rows if not r['c']))
EOF
```
Expected: `B` ≈ 9.076 y `A` ≈ 868 (±1% por refrescos de la tabla); las etapas B deben reproducir la tabla de `OPORTUNIDADES.md` §1 (5.325 / 532 / 1.571 / 448 / ~140 / ~1.060). Si `B` difiere > 2%, la cohorte cambió: anotarlo en el informe, no "corregir" la query.

- [ ] **Step 4: Confirmar que el JSON NO está trackeado y commitear la query**

```bash
cd ~/habi/tableros-marketing-habi && git status --short analisis-gabi-completitud/bugs/
```
Expected: no aparece `bugs/data/convs.json`. Si aparece, revisar `bugs/.gitignore` antes de seguir.

```bash
git add analisis-gabi-completitud/queries/export_conversaciones.sql
git commit -m "analisis(gabi): query de export de conversaciones (bots A y B) para deteccion de bugs"
```

---

### Task 2: Parser de turnos (TDD)

**Files:**
- Create: `bugs/parse.py`
- Test: `bugs/tests/test_parse.py`

- [ ] **Step 1: Escribir los tests fallidos**

`bugs/tests/test_parse.py`:
```python
from datetime import datetime
from parse import parse_turns, redact, is_nudge

C = (
    "Gabi: ¡Hola, Lulu Cruz! *Recibimos tu solicitud*\n\n"
    "📌 ¿Podrías indicarnos si es *casa o departamento*?. HORA: 2026-06-06T13:50:12.434779\n"
    "Usuario: Metepec Edo mex.\nRafias\n703\n52150. HORA: 2026-06-06T13:55:55.904087\n"
    "Gabi: *Sigo pendiente de tu respuesta*\n\n📌 Cuando tengas oportunidad.. HORA: 2026-06-06T15:50:12.316071"
)

def test_parse_separa_turnos_y_roles():
    t = parse_turns(C)
    assert [x.rol for x in t] == ["gabi", "usuario", "gabi"]

def test_parse_conserva_saltos_de_linea_del_usuario():
    t = parse_turns(C)
    assert t[1].texto == "Metepec Edo mex.\nRafias\n703\n52150"

def test_parse_extrae_hora_y_quita_el_sufijo():
    t = parse_turns(C)
    assert t[0].hora == datetime(2026, 6, 6, 13, 50, 12, 434779)
    assert "HORA" not in t[0].texto

def test_parse_sin_hora_da_none():
    t = parse_turns("Gabi: hola\nUsuario: ok")
    assert t[1].hora is None and t[1].texto == "ok"

def test_parse_indices_consecutivos():
    assert [x.idx for x in parse_turns(C)] == [0, 1, 2]

def test_is_nudge():
    assert is_nudge("*Sigo pendiente de tu respuesta*\n\n📌 Cuando tengas oportunidad")
    assert not is_nudge("¡Anotado! Ya quedó la *dirección*")

def test_redact_nombre_telefono_email():
    s = redact("¡Hola, Lulu Cruz! llámame al 55 1234 5678 o a lulu@mail.com")
    assert "Lulu" not in s and "1234" not in s and "@" not in s
```

- [ ] **Step 2: Correr para verificar que fallan**

```bash
cd ~/habi/tableros-marketing-habi/analisis-gabi-completitud && bugs/.venv/bin/pytest bugs/tests/test_parse.py -q
```
Expected: `ModuleNotFoundError: No module named 'parse'`.

- [ ] **Step 3: Implementar el parser**

`bugs/parse.py`:
```python
"""Convierte la conversación cruda de mabi_mx (texto con 'Gabi:'/'Usuario:' + 'HORA:') en turnos."""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

_SPLIT = re.compile(r'\n(?=Gabi:|Usuario:)')
_HORA = re.compile(r'HORA: ([\d\-T:.]+)')
_SUFIJO_HORA = re.compile(r'\.?\s*HORA: [\d\-T:.]+\s*$')
_NUDGE = re.compile(r'Sigo pendiente de tu respuesta', re.I)


@dataclass
class Turn:
    idx: int
    rol: str            # 'gabi' | 'usuario'
    texto: str
    hora: Optional[datetime]


def _parse_hora(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s.rstrip('.'))
    except ValueError:
        return None


def parse_turns(c: str) -> list[Turn]:
    turns = []
    for bloque in _SPLIT.split(c or ''):
        bloque = bloque.strip()
        if not bloque:
            continue
        m = _HORA.search(bloque)
        hora = _parse_hora(m.group(1)) if m else None
        texto = _SUFIJO_HORA.sub('', bloque).strip()
        rol, _, cuerpo = texto.partition(':')
        rol = rol.strip().lower()
        if rol not in ('gabi', 'usuario'):
            continue  # basura entre turnos: no la contamos como turno
        turns.append(Turn(len(turns), rol, cuerpo.strip(), hora))
    return turns


def is_nudge(texto: str) -> bool:
    return bool(_NUDGE.search(texto))


def redact(t: str) -> str:
    """Quita nombre del saludo, emails y teléfonos. Suficiente para muestras internas; NO anonimiza direcciones."""
    t = re.sub(r'¡?Hola,?\s+[^!\n*]{2,60}!', '¡Hola, [nombre]!', t)
    t = re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+', '[email]', t)
    t = re.sub(r'\+?\d[\d\s().-]{8,}\d',
               lambda m: '[tel]' if len(re.sub(r'\D', '', m.group())) >= 10 else m.group(), t)
    return t
```

- [ ] **Step 4: Correr los tests**

```bash
bugs/.venv/bin/pytest bugs/tests/test_parse.py -q
```
Expected: `7 passed`.

- [ ] **Step 5: Humo contra los datos reales**

```bash
python3 - <<'EOF'
import json, collections, sys
sys.path.insert(0, 'bugs')
from parse import parse_turns
rows = json.load(open('bugs/data/convs.json'))
n_turnos = collections.Counter(); sin_hora = 0
for r in rows:
    t = parse_turns(r['c'])
    n_turnos[len(t)] += 1
    sin_hora += sum(1 for x in t if x.hora is None)
print('convs con 0 turnos:', n_turnos[0], '| mediana turnos:', sorted(n_turnos.elements())[len(rows)//2])
print('turnos sin HORA:', sin_hora)
EOF
```
Expected: 0 conversaciones con 0 turnos; turnos sin HORA cercanos a 0. Si hay muchos sin HORA, mirar 3 ejemplos y ajustar `_HORA` antes de seguir (los detectores de latencia dependen de eso).

- [ ] **Step 6: Commit**

```bash
git add bugs/parse.py bugs/tests/test_parse.py
git commit -m "analisis(gabi): parser de turnos (rol, texto, hora) + redaccion para muestras"
```

---

### Task 3: Detectores estructurales y técnicos (tipos 6–12, TDD)

**Files:**
- Create: `bugs/detectores.py`
- Test: `bugs/tests/test_detectores.py`

Convención: cada detector es `det_<tipo>(turns: list[Turn], bot: str) -> list[dict]` y cada hallazgo es `{"tipo": str, "subtipo": str|None, "idx": int, "evidencia": str}` (`evidencia` ≤ 200 chars del turno que dispara). Los detectores no leen `bot` salvo que lo necesiten; aceptarlo siempre mantiene una sola firma.

- [ ] **Step 1: Tests fallidos para los detectores estructurales**

`bugs/tests/test_detectores.py`:
```python
from datetime import datetime, timedelta
from parse import Turn
import detectores as D

T0 = datetime(2026, 7, 1, 10, 0, 0)

def mk(*pares):
    """mk(('g', 'texto', minutos), ('u', 'texto', minutos), ...) -> list[Turn]"""
    out = []
    for i, (rol, texto, mins) in enumerate(pares):
        out.append(Turn(i, 'gabi' if rol == 'g' else 'usuario', texto, T0 + timedelta(minutes=mins)))
    return out

NUDGE = "*Sigo pendiente de tu respuesta*\n\n📌 Cuando tengas oportunidad"
BLOQUE = "Ahora ayúdame con estos datos:\n📅 *Antigüedad* en años\n📏 *Área construida* en m²\n🛏️ *Recámaras*\n🛁 *Baños*\n🚗 *Cajones*\n💰 *Valor que pides*"

# --- 6 silencio_bot ---
def test_silencio_bot_ultimo_turno_usuario():
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1))
    h = D.det_silencio_bot(t, 'B')
    assert [x['tipo'] for x in h] == ['silencio_bot'] and h[0]['subtipo'] == 'sin_respuesta_final'

def test_silencio_bot_solo_nudge():
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1), ('g', NUDGE, 121))
    assert D.det_silencio_bot(t, 'B')[0]['subtipo'] == 'solo_nudge'

def test_silencio_bot_no_dispara_si_gabi_contesta():
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1), ('g', '¡Perfecto! Ya anoté', 2))
    assert D.det_silencio_bot(t, 'B') == []

# --- 7 nudge_anomalo ---
def test_nudge_tras_respuesta_del_usuario():
    t = mk(('g', BLOQUE, 0), ('u', '10 años, 120 m2, 3, 2, 1, 2 millones', 3), ('g', NUDGE, 120))
    h = D.det_nudge_anomalo(t, 'B')
    assert h and h[0]['subtipo'] == 'nudge_tras_usuario'

def test_nudge_doble():
    t = mk(('g', BLOQUE, 0), ('g', NUDGE, 120), ('g', NUDGE, 240))
    assert any(x['subtipo'] == 'nudge_doble' for x in D.det_nudge_anomalo(t, 'B'))

def test_nudge_normal_no_dispara():
    t = mk(('g', BLOQUE, 0), ('g', NUDGE, 120))
    assert D.det_nudge_anomalo(t, 'B') == []

# --- 8 loop_repeticion ---
def test_loop_mismo_mensaje_dos_veces():
    t = mk(('g', 'Compárteme la *dirección*', 0), ('u', 'Calle 5', 1), ('g', 'Compárteme la *dirección*', 2))
    assert D.det_loop_repeticion(t, 'B')[0]['subtipo'] == 'mensaje_repetido'

def test_loop_ignora_el_nudge():
    t = mk(('g', BLOQUE, 0), ('g', NUDGE, 120), ('g', NUDGE, 1560))
    assert all(x['subtipo'] != 'mensaje_repetido' for x in D.det_loop_repeticion(t, 'B'))

def test_loop_mismo_campo_tres_veces():
    f = "Solo me falta la *área construida* en m²"
    t = mk(('g', f, 0), ('u', 'no sé', 1), ('g', f + ' 😊', 2), ('u', 'mmm', 3), ('g', f + '!!', 4))
    assert any(x['subtipo'] == 'campo_repreguntado_3x' for x in D.det_loop_repeticion(t, 'B'))

# --- 9 duplicado_gabi ---
def test_duplicado_gabi_mismo_texto_en_1_min():
    t = mk(('g', 'hola', 0), ('g', 'hola', 1))
    assert D.det_duplicado_gabi(t, 'B')[0]['tipo'] == 'duplicado_gabi'

def test_duplicado_gabi_no_si_pasan_5_min():
    t = mk(('g', 'hola', 0), ('g', 'hola', 5))
    assert D.det_duplicado_gabi(t, 'B') == []

# --- 10 plantilla_rota ---
def test_plantilla_rota_none_y_llaves():
    assert D.det_plantilla_rota(mk(('g', '¡Hola, None! bienvenido', 0)), 'B')
    assert D.det_plantilla_rota(mk(('g', 'Hola {nombre}', 0)), 'B')
    assert D.det_plantilla_rota(mk(('g', '¡Hola, !', 0)), 'B')

def test_plantilla_rota_no_falsos_positivos_en_usuario():
    assert D.det_plantilla_rota(mk(('u', 'None', 0)), 'B') == []

# --- 11 hora_no_monotona ---
def test_hora_no_monotona():
    t = mk(('g', 'a', 10), ('u', 'b', 5))
    assert D.det_hora_no_monotona(t, 'B')[0]['tipo'] == 'hora_no_monotona'

# --- 12 latencia_alta ---
def test_latencia_alta_gabi_tarda_mas_de_10_min():
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1), ('g', '¡Perfecto!', 15))
    assert D.det_latencia_alta(t, 'B')[0]['tipo'] == 'latencia_alta'

def test_latencia_alta_ignora_nudge():
    t = mk(('g', 'hola', 0), ('u', 'Casa', 1), ('g', NUDGE, 121))
    assert D.det_latencia_alta(t, 'B') == []
```

- [ ] **Step 2: Verificar que fallan**

```bash
bugs/.venv/bin/pytest bugs/tests/test_detectores.py -q
```
Expected: `ModuleNotFoundError: No module named 'detectores'`.

- [ ] **Step 3: Implementar los detectores estructurales**

`bugs/detectores.py` (primera versión; la Task 4 agrega los de contenido al mismo archivo):
```python
"""Detectores de fallas del agente. Cada det_<tipo>(turns, bot) -> list[hallazgo].
hallazgo = {"tipo", "subtipo", "idx", "evidencia"}. Regex sobre texto de LLM: validar SIEMPRE con muestra (Task 6)."""
import re
import unicodedata
from parse import Turn, is_nudge

# ---------- constantes compartidas ----------
FALTA = {   # campo -> regex del "Solo me falta ... <campo>" del bot B
    'area':       r'[áa]rea construida',
    'precio':     r'valor|precio',
    'antiguedad': r'antig[üu]edad',
    'recamaras':  r'rec[áa]maras',
    'banos':      r'ba[ñn]os',
    'cajones':    r'cajones|estacionamiento',
}
RE_FALTA = {k: re.compile(r'falta[\s\S]{0,200}?(' + v + ')', re.I) for k, v in FALTA.items()}
RE_PLANTILLA_ROTA = re.compile(r'\bNone\b|\bnull\b|\bnan\b|\{\{|\{[a-z_]+\}|\bundefined\b|\[object|¡Hola, !|Hola, ,', re.I)
LATENCIA_MAX_S = 600
DUPLICADO_MAX_S = 120


def _h(tipo, turn, subtipo=None):
    return {'tipo': tipo, 'subtipo': subtipo, 'idx': turn.idx, 'evidencia': turn.texto[:200]}


def _norm(texto: str) -> str:
    """Minúsculas, sin acentos, sin emojis/puntuación, sin nombre del saludo. Para comparar mensajes de Gabi."""
    t = re.sub(r'¡?Hola,?\s+[^!\n*]{2,60}!', 'hola', texto)
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9 ]+', ' ', t.lower()).strip()


def _dt(a: Turn, b: Turn):
    if a.hora is None or b.hora is None:
        return None
    return (b.hora - a.hora).total_seconds()


# ---------- 6 silencio_bot ----------
def det_silencio_bot(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario':
            continue
        despues = turns[i + 1:]
        if not despues:
            out.append(_h('silencio_bot', t, 'sin_respuesta_final'))
        elif all(x.rol == 'gabi' and is_nudge(x.texto) for x in despues):
            out.append(_h('silencio_bot', t, 'solo_nudge'))
    return out


# ---------- 7 nudge_anomalo ----------
def det_nudge_anomalo(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'gabi' or not is_nudge(t.texto) or i == 0:
            continue
        prev = turns[i - 1]
        if prev.rol == 'usuario':
            out.append(_h('nudge_anomalo', t, 'nudge_tras_usuario'))
        elif prev.rol == 'gabi' and is_nudge(prev.texto):
            out.append(_h('nudge_anomalo', t, 'nudge_doble'))
    return out


# ---------- 8 loop_repeticion ----------
def det_loop_repeticion(turns, bot):
    out, vistos = [], {}
    for t in turns:
        if t.rol != 'gabi' or is_nudge(t.texto):
            continue
        k = _norm(t.texto)
        if len(k) > 20 and k in vistos:
            out.append(_h('loop_repeticion', t, 'mensaje_repetido'))
        vistos[k] = t.idx
    for campo, rx in RE_FALTA.items():
        veces = [t for t in turns if t.rol == 'gabi' and rx.search(t.texto)]
        if len(veces) >= 3:
            out.append(_h('loop_repeticion', veces[2], 'campo_repreguntado_3x'))
    return out


# ---------- 9 duplicado_gabi ----------
def det_duplicado_gabi(turns, bot):
    out = []
    for a, b in zip(turns, turns[1:]):
        if a.rol == b.rol == 'gabi' and a.texto == b.texto:
            d = _dt(a, b)
            if d is not None and d < DUPLICADO_MAX_S:
                out.append(_h('duplicado_gabi', b))
    return out


# ---------- 10 plantilla_rota ----------
def det_plantilla_rota(turns, bot):
    return [_h('plantilla_rota', t) for t in turns if t.rol == 'gabi' and RE_PLANTILLA_ROTA.search(t.texto)]


# ---------- 11 hora_no_monotona ----------
def det_hora_no_monotona(turns, bot):
    out = []
    for a, b in zip(turns, turns[1:]):
        d = _dt(a, b)
        if d is not None and d < 0:
            out.append(_h('hora_no_monotona', b))
    return out


# ---------- 12 latencia_alta ----------
def det_latencia_alta(turns, bot):
    out = []
    for a, b in zip(turns, turns[1:]):
        if a.rol == 'usuario' and b.rol == 'gabi' and not is_nudge(b.texto):
            d = _dt(a, b)
            if d is not None and d > LATENCIA_MAX_S:
                out.append(_h('latencia_alta', b, f'{int(d // 60)}min'))
    return out


TODOS = [det_silencio_bot, det_nudge_anomalo, det_loop_repeticion, det_duplicado_gabi,
         det_plantilla_rota, det_hora_no_monotona, det_latencia_alta]
```

- [ ] **Step 4: Correr los tests**

```bash
bugs/.venv/bin/pytest bugs/tests -q
```
Expected: `23 passed` (7 de parse + 16 de detectores).

- [ ] **Step 5: Commit**

```bash
git add bugs/detectores.py bugs/tests/test_detectores.py
git commit -m "analisis(gabi): detectores estructurales (silencio, nudge anomalo, loops, duplicados, plantilla rota, latencia)"
```

---

### Task 4: Detectores de contenido (tipos 1–5, TDD)

**Files:**
- Modify: `bugs/detectores.py` (agregar al final, antes de `TODOS`)
- Modify: `bugs/tests/test_detectores.py` (agregar tests)

- [ ] **Step 1: Calibrar los regex contra los datos reales ANTES de fijarlos**

Este paso es exploratorio y no se commitea. Su función es ver cómo se ven de verdad las preguntas, los adjuntos y los opt-outs para que los patrones no sean inventados.

```bash
python3 - <<'EOF'
import json, re, sys, collections, random
sys.path.insert(0, 'bugs')
from parse import parse_turns, redact
rows = json.load(open('bugs/data/convs.json')); random.seed(7)
usr = [(r['bot'], t.texto) for r in rows for t in parse_turns(r['c']) if t.rol == 'usuario']
print('turnos de usuario:', len(usr))
def muestra(nombre, rx, n=15):
    hits = [x for x in usr if re.search(rx, x[1], re.I)]
    print(f'\n### {nombre}: {len(hits)} turnos ({100*len(hits)/len(usr):.1f}%)')
    for b, x in random.sample(hits, min(n, len(hits))): print(f'  [{b}] {redact(x)[:160]!r}')
muestra('con ?', r'\?|¿')
muestra('vacios o adjuntos', r'^\s*$|\.(jpe?g|png|ogg|opus|mp4|pdf)\b|maps\.|\[(imagen|audio|video|ubicaci|documento|sticker)')
muestra('opt-out', r'ya (lo |la )?vend|no me interesa|no quiero|dej(a|en) de|equivocad')
muestra('pide humano/oferta', r'asesor|humano|persona|ll[aá]m|tel[eé]fono|cu[aá]nto (me )?(dan|ofrecen|pagan)|oferta|visita|cita')
muestra('ambiguo', r'no s[eé]|aprox|m[aá]s o menos|creo que|no recuerdo|no tengo|depende')
EOF
```
Anotar en un comentario al tope de cada regex de la sección siguiente qué variantes reales aparecieron (p. ej. cómo se ve una ubicación de WhatsApp en `messages`: ¿turno vacío?, ¿URL de maps?, ¿`[ubicación]`?). Si los adjuntos NO dejan rastro en el texto, `media_no_manejado` se degrada a "no medible" y se dice así en el informe.

- [ ] **Step 2: Tests fallidos para los detectores de contenido**

Agregar al final de `bugs/tests/test_detectores.py`:
```python
GUION_DIR = "¡Perfecto! 🏡 Ya anoté que es una *casa*.\n\nAhora compárteme la *dirección* en texto, por favor:\n📍 *Estado*\n🛣️ *Calle*"
ACK = "¡Gracias! 🙌 Ya registré la *antigüedad*, *recámaras*, *baños*, *cajones* y el *valor pedido*."

# --- 1 pregunta_ignorada ---
def test_pregunta_ignorada_bot_b_responde_con_guion():
    t = mk(('g', 'hola', 0), ('u', '¿Cuánto me ofrecen por mi casa?', 1), ('g', GUION_DIR, 2))
    h = D.det_pregunta_ignorada(t, 'B')
    assert h and h[0]['tipo'] == 'pregunta_ignorada' and h[0]['idx'] == 1

def test_pregunta_ignorada_bot_b_responde_con_nudge():
    t = mk(('g', 'hola', 0), ('u', 'y cuánto tardan?', 1), ('g', NUDGE, 121))
    assert D.det_pregunta_ignorada(t, 'B')[0]['subtipo'] == 'siguio_nudge'

def test_pregunta_ignorada_no_dispara_si_gabi_sale_del_guion():
    t = mk(('g', 'hola', 0), ('u', '¿Cuánto tardan?', 1), ('g', 'La evaluación toma 48 horas hábiles.', 2))
    assert D.det_pregunta_ignorada(t, 'B') == []

def test_pregunta_ignorada_bot_a_solo_marca_candidata():
    t = mk(('g', 'hola', 0), ('u', '¿Cuánto tardan?', 1), ('g', 'Necesito la dirección.', 2))
    assert D.det_pregunta_ignorada(t, 'A')[0]['subtipo'] == 'candidata_llm'

def test_pregunta_ignorada_ignora_respuesta_corta_con_signo():
    t = mk(('g', BLOQUE, 0), ('u', '3?', 1), ('g', ACK, 2))
    assert D.det_pregunta_ignorada(t, 'B') == []

# --- 2 ambigua_registrada ---
def test_ambigua_registrada_no_se_y_ack():
    t = mk(('g', BLOQUE, 0), ('u', 'no sé los metros, como 10 años, 3 recámaras', 1), ('g', ACK, 2))
    assert D.det_ambigua_registrada(t, 'B')[0]['subtipo'] == 'marcador_ambiguo'

def test_ambigua_registrada_sin_numeros_tras_bloque():
    t = mk(('g', BLOQUE, 0), ('u', 'es grande, tiene varias recámaras', 1), ('g', ACK, 2))
    assert D.det_ambigua_registrada(t, 'B')[0]['subtipo'] == 'sin_numeros'

def test_ambigua_no_dispara_si_gabi_repregunta():
    t = mk(('g', BLOQUE, 0), ('u', 'no sé los metros', 1), ('g', 'Solo me falta la *área construida*', 2))
    assert D.det_ambigua_registrada(t, 'B') == []

# --- 3 repregunta_dato_ya_dado ---
def test_repregunta_area_ya_dada():
    t = mk(('g', BLOQUE, 0), ('u', '10 años\n120 m2\n3\n2\n1\n2,500,000', 1), ('g', 'Solo me falta la *área construida* en m²', 2))
    h = D.det_repregunta_dato_ya_dado(t, 'B')
    assert h and h[0]['subtipo'] == 'area'

def test_repregunta_precio_ya_dado():
    t = mk(('g', BLOQUE, 0), ('u', '10 años, 120 m2, 3, 2, 1, $2,500,000', 1), ('g', 'Solo me falta el *valor* que pides', 2))
    assert D.det_repregunta_dato_ya_dado(t, 'B')[0]['subtipo'] == 'precio'

def test_repregunta_no_dispara_si_el_dato_no_estaba():
    t = mk(('g', BLOQUE, 0), ('u', '10 años, 3, 2, 1, 2,500,000', 1), ('g', 'Solo me falta la *área construida*', 2))
    assert D.det_repregunta_dato_ya_dado(t, 'B') == []

# --- 4 intencion_ignorada ---
def test_intencion_optout_seguida_de_guion():
    t = mk(('g', 'hola', 0), ('u', 'ya vendí la casa, gracias', 1), ('g', GUION_DIR, 2))
    assert D.det_intencion_ignorada(t, 'B')[0]['subtipo'] == 'opt_out'

def test_intencion_humano_seguida_de_nudge():
    t = mk(('g', 'hola', 0), ('u', 'prefiero que me llame un asesor', 1), ('g', NUDGE, 121))
    assert D.det_intencion_ignorada(t, 'B')[0]['subtipo'] == 'pide_humano'

def test_intencion_no_dispara_si_gabi_la_atiende():
    t = mk(('g', 'hola', 0), ('u', 'ya vendí', 1), ('g', 'Entendido, cerramos tu solicitud. ¡Éxitos!', 2))
    assert D.det_intencion_ignorada(t, 'B') == []

# --- 5 media_no_manejado ---
def test_media_url_maps_seguida_de_guion():
    t = mk(('g', GUION_DIR, 0), ('u', 'https://maps.google.com/?q=19.4,-99.1', 1), ('g', GUION_DIR, 2))
    assert D.det_media_no_manejado(t, 'B')[0]['tipo'] == 'media_no_manejado'

def test_media_turno_vacio_seguido_de_guion():
    t = mk(('g', GUION_DIR, 0), ('u', '', 1), ('g', GUION_DIR, 2))
    assert D.det_media_no_manejado(t, 'B')[0]['subtipo'] == 'vacio'
```

- [ ] **Step 3: Verificar que fallan**

```bash
bugs/.venv/bin/pytest bugs/tests/test_detectores.py -q
```
Expected: 16 fallos `AttributeError: module 'detectores' has no attribute 'det_pregunta_ignorada'` (y similares).

- [ ] **Step 4: Implementar los detectores de contenido**

Insertar en `bugs/detectores.py` justo antes de `TODOS = [...]`, y actualizar `TODOS`:
```python
# ---------- constantes de contenido (ajustar con lo visto en la calibración del Step 1) ----------
RE_GUION_B = re.compile(
    r'Ya anot[ée]|Ya registr[ée]|¡Anotado|comp[áa]rteme la \*direcci[óo]n\*|Ahora ay[úu]dame con estos datos'
    r'|Solo me falta|necesitamos algunos datos del inmueble|casa o departamento', re.I)
RE_PREGUNTA = re.compile(r'\?|¿|(?<!\w)(cu[áa]nto|cu[áa]ndo|c[óo]mo|qu[ée]|qui[ée]n|d[óo]nde|por qu[ée]|para qu[ée])(?!\w)', re.I)
RE_AMBIGUO = re.compile(
    r'(?<!\w)(no (lo )?s[ée]|aprox\w*|m[áa]s o menos|creo que|no recuerdo|no tengo (el|la|los|idea)|depende'
    r'|no estoy segur|alrededor de|como unos?|unos \d|entre \d)', re.I)
RE_ACK = re.compile(r'^\W*(Perfecto|Gracias|Anotado|Excelente|Genial|Listo|Ya anot|Ya registr)', re.I)
RE_ACLARA = re.compile(r'falta|confirm|aclar|podr[íi]as (indicar|decir|compartir)|¿me (compartes|confirmas)|no (logr|pud)', re.I)
RE_BLOQUE = re.compile(r'\*antig[üu]edad\*', re.I)
CAMPOS_USUARIO = {   # cómo se ve el dato cuando el usuario lo escribe
    'area':       re.compile(r'\d+\s*(m2|m²|mts?\b|metros)', re.I),
    'precio':     re.compile(r'\$\s?\d|\d[\d.,\s]{6,}\d|mill[óo]n|mdp|\b\d+\s*mil\b', re.I),
    'antiguedad': re.compile(r'\d+\s*a[ñn]os', re.I),
    'recamaras':  re.compile(r'rec[áa]mara|habitaci|cuarto|dormitorio', re.I),
    'banos':      re.compile(r'ba[ñn]o', re.I),
    'cajones':    re.compile(r'caj[óo]n|estacionamiento|cochera|garaje|garage', re.I),
}
RE_OPT_OUT = re.compile(
    r'(?<!\w)(ya (lo |la |se )?vend[ií]|ya no (me interesa|quiero|est[áa] en venta|lo vendo)|no me interesa'
    r'|no (quiero|deseo|pienso) vender|dej(a|en|ame) de (escribir|molestar|mandar)|no (me )?(escriban|molesten)'
    r'|n[úu]mero equivocado|no soy (el|la) due|no solicit[ée]|no ped[íi])', re.I)
RE_HUMANO = re.compile(
    r'(?<!\w)(asesor|humano|una persona|alguien (real|que)|ejecutivo|agente|ll[áa]m(a|e)me|me pueden llamar'
    r'|hablar con|un tel[ée]fono|cu[áa]nto (me )?(dan|ofrecen|pagan|vale)|cu[áa]l es la oferta|cu[áa]ndo (me )?visitan)', re.I)
RE_MEDIA = re.compile(r'\.(jpe?g|png|ogg|opus|mp4|pdf)\b|maps\.(google|app)|goo\.gl/maps|\[(imagen|audio|video|ubicaci[óo]n|documento|sticker|archivo)\]', re.I)


def _siguiente_gabi(turns, i):
    for t in turns[i + 1:]:
        if t.rol == 'gabi':
            return t
    return None


def _clasifica_respuesta_gabi(g):
    """'nudge' | 'guion' | 'libre' | None (sin respuesta)."""
    if g is None:
        return None
    if is_nudge(g.texto):
        return 'nudge'
    if RE_GUION_B.search(g.texto):
        return 'guion'
    return 'libre'


# ---------- 1 pregunta_ignorada ----------
def det_pregunta_ignorada(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario' or not RE_PREGUNTA.search(t.texto) or len(t.texto.split()) < 3:
            continue   # '3?' o 'si?' no son preguntas de verdad
        r = _clasifica_respuesta_gabi(_siguiente_gabi(turns, i))
        if r is None:
            continue   # ya lo cubre silencio_bot
        if r == 'nudge':
            out.append(_h('pregunta_ignorada', t, 'siguio_nudge'))
        elif r == 'guion' and bot == 'B':
            out.append(_h('pregunta_ignorada', t, 'siguio_guion'))
        elif bot == 'A':
            out.append(_h('pregunta_ignorada', t, 'candidata_llm'))   # el LLM libre "responde" siempre: juzgar aparte
    return out


# ---------- 2 ambigua_registrada ----------
def det_ambigua_registrada(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario' or i == 0:
            continue
        g = _siguiente_gabi(turns, i)
        if g is None or is_nudge(g.texto) or not RE_ACK.search(g.texto) or RE_ACLARA.search(g.texto):
            continue   # Gabi no acusó recibo, o sí re-preguntó: no es el bug
        prev = turns[i - 1]
        if RE_AMBIGUO.search(t.texto):
            out.append(_h('ambigua_registrada', t, 'marcador_ambiguo'))
        elif prev.rol == 'gabi' and RE_BLOQUE.search(prev.texto) and not re.search(r'\d', t.texto):
            out.append(_h('ambigua_registrada', t, 'sin_numeros'))
    return out


# ---------- 3 repregunta_dato_ya_dado ----------
def det_repregunta_dato_ya_dado(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'gabi':
            continue
        for campo, rx in RE_FALTA.items():
            if not rx.search(t.texto):
                continue
            # texto del usuario desde el último pedido de bloque hasta esta re-pregunta
            ini = max([j for j in range(i) if turns[j].rol == 'gabi' and RE_BLOQUE.search(turns[j].texto)] or [0])
            dicho = '\n'.join(x.texto for x in turns[ini:i] if x.rol == 'usuario')
            if CAMPOS_USUARIO[campo].search(dicho):
                out.append(_h('repregunta_dato_ya_dado', t, campo))
    return out


# ---------- 4 intencion_ignorada ----------
def det_intencion_ignorada(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario':
            continue
        sub = 'opt_out' if RE_OPT_OUT.search(t.texto) else 'pide_humano' if RE_HUMANO.search(t.texto) else None
        if sub is None:
            continue
        r = _clasifica_respuesta_gabi(_siguiente_gabi(turns, i))
        if r in ('nudge', 'guion'):
            out.append(_h('intencion_ignorada', t, sub))
    return out


# ---------- 5 media_no_manejado ----------
def det_media_no_manejado(turns, bot):
    out = []
    for i, t in enumerate(turns):
        if t.rol != 'usuario':
            continue
        sub = 'vacio' if not t.texto.strip() else 'adjunto_o_url' if RE_MEDIA.search(t.texto) else None
        if sub is None:
            continue
        if _clasifica_respuesta_gabi(_siguiente_gabi(turns, i)) in ('nudge', 'guion'):
            out.append(_h('media_no_manejado', t, sub))
    return out


TODOS = [det_pregunta_ignorada, det_ambigua_registrada, det_repregunta_dato_ya_dado, det_intencion_ignorada,
         det_media_no_manejado, det_silencio_bot, det_nudge_anomalo, det_loop_repeticion, det_duplicado_gabi,
         det_plantilla_rota, det_hora_no_monotona, det_latencia_alta]
```
(Borrar la asignación anterior de `TODOS` que quedó de la Task 3: debe haber una sola.)

- [ ] **Step 5: Correr todos los tests**

```bash
bugs/.venv/bin/pytest bugs/tests -q
```
Expected: `39 passed` (7 + 16 + 16).

- [ ] **Step 6: Commit**

```bash
git add bugs/detectores.py bugs/tests/test_detectores.py
git commit -m "analisis(gabi): detectores de contenido (pregunta ignorada, ambigua registrada, dato repreguntado, intencion, media)"
```

---

### Task 5: Runner, agregados y cruce con el funnel

**Files:**
- Create: `bugs/run.py`
- Test: `bugs/tests/test_run.py`
- Genera: `bugs/data/hallazgos.jsonl` (ignorado), `bugs/resumen.json` (commiteable)

- [ ] **Step 1: Test fallido del agregador**

`bugs/tests/test_run.py`:
```python
from run import agregar

def test_agregar_cuenta_convs_no_hallazgos_y_cruza_ruteo():
    convs = [
        {'deal_id': 1, 'bot': 'B', 'etapa_muerte': '3_murio_en_direccion', 'ruteado': 0,
         'hallazgos': [{'tipo': 'pregunta_ignorada'}, {'tipo': 'pregunta_ignorada'}]},
        {'deal_id': 2, 'bot': 'B', 'etapa_muerte': '6_completo_o_paso', 'ruteado': 1, 'hallazgos': []},
        {'deal_id': 3, 'bot': 'A', 'etapa_muerte': '7_completo', 'ruteado': 1,
         'hallazgos': [{'tipo': 'silencio_bot'}]},
    ]
    r = agregar(convs)
    assert r['total']['convs'] == {'A': 1, 'B': 2}
    pi = r['por_tipo']['pregunta_ignorada']
    assert pi['hallazgos'] == 2 and pi['convs'] == {'B': 1}
    assert pi['pct_convs']['B'] == 50.0
    assert pi['por_etapa']['B']['3_murio_en_direccion'] == 1
    assert pi['ruteo']['con_bug'] == 0.0 and pi['ruteo']['sin_bug'] == 100.0
```

- [ ] **Step 2: Verificar que falla**

```bash
bugs/.venv/bin/pytest bugs/tests/test_run.py -q
```
Expected: `ModuleNotFoundError: No module named 'run'`.

- [ ] **Step 3: Implementar el runner**

`bugs/run.py`:
```python
"""Corre todos los detectores sobre bugs/data/convs.json.
Escribe bugs/data/hallazgos.jsonl (con PII, ignorado) y bugs/resumen.json (agregados, se commitea)."""
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse import parse_turns, is_nudge   # noqa: E402
import detectores as D                     # noqa: E402

HERE = Path(__file__).resolve().parent
CONVS = HERE / 'data' / 'convs.json'
HALLAZGOS = HERE / 'data' / 'hallazgos.jsonl'
RESUMEN = HERE / 'resumen.json'


def procesar(row):
    turns = parse_turns(row['c'])
    hallazgos = []
    for det in D.TODOS:
        hallazgos.extend(det(turns, row['bot']))
    lat = [D._dt(a, b) for a, b in zip(turns, turns[1:])
           if a.rol == 'usuario' and b.rol == 'gabi' and not is_nudge(b.texto)]
    return {
        'deal_id': row['deal_id'], 'bot': row['bot'], 'etapa_muerte': row['etapa_muerte'],
        'ruteado': 1 if (int(row['agendo']) or int(row['inmo'])) else 0,
        'n_turnos': len(turns), 'n_usuario': sum(1 for t in turns if t.rol == 'usuario'),
        'latencias_s': [x for x in lat if x is not None],
        'hallazgos': hallazgos,
    }


def agregar(convs):
    total = Counter(c['bot'] for c in convs)
    r = {'total': {'convs': dict(total)}, 'por_tipo': {}}
    tipos = sorted({h['tipo'] for c in convs for h in c['hallazgos']})
    for tipo in tipos:
        con = [c for c in convs if any(h['tipo'] == tipo for h in c['hallazgos'])]
        sin = [c for c in convs if c not in con]
        por_bot = Counter(c['bot'] for c in con)
        por_etapa = defaultdict(Counter)
        for c in con:
            por_etapa[c['bot']][c['etapa_muerte']] += 1
        subtipos = Counter(h.get('subtipo') or '-' for c in con for h in c['hallazgos'] if h['tipo'] == tipo)
        r['por_tipo'][tipo] = {
            'hallazgos': sum(1 for c in convs for h in c['hallazgos'] if h['tipo'] == tipo),
            'convs': dict(por_bot),
            'pct_convs': {b: round(100 * por_bot[b] / total[b], 1) for b in por_bot},
            'subtipos': dict(subtipos),
            'por_etapa': {b: dict(v) for b, v in por_etapa.items()},
            'ruteo': {
                'con_bug': round(100 * sum(c['ruteado'] for c in con) / max(len(con), 1), 1),
                'sin_bug': round(100 * sum(c['ruteado'] for c in sin) / max(len(sin), 1), 1),
            },
        }
    return r


def main():
    rows = json.load(open(CONVS))
    convs = [procesar(r) for r in rows]
    with open(HALLAZGOS, 'w') as f:
        for c in convs:
            for h in c['hallazgos']:
                f.write(json.dumps({'deal_id': c['deal_id'], 'bot': c['bot'], 'etapa_muerte': c['etapa_muerte'],
                                    'ruteado': c['ruteado'], **h}, ensure_ascii=False) + '\n')
    resumen = agregar(convs)
    lat = defaultdict(list)
    for c in convs:
        lat[c['bot']].extend(c['latencias_s'])
    resumen['latencia_gabi_s'] = {b: {'mediana': round(statistics.median(v)), 'p90': round(sorted(v)[int(.9 * len(v))]),
                                      'n': len(v)} for b, v in lat.items() if v}
    resumen['convs_con_respuesta'] = dict(Counter(c['bot'] for c in convs if c['n_usuario'] > 0))
    json.dump(resumen, open(RESUMEN, 'w'), ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in resumen.items() if k != 'por_tipo'}, ensure_ascii=False))
    for tipo, v in resumen['por_tipo'].items():
        print(f"{tipo:<26} hallazgos={v['hallazgos']:>5}  convs={v['convs']}  pct={v['pct_convs']}  ruteo con/sin={v['ruteo']['con_bug']}/{v['ruteo']['sin_bug']}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Correr tests y luego el runner real**

```bash
bugs/.venv/bin/pytest bugs/tests -q && python3 bugs/run.py
```
Expected: `40 passed`; luego una línea por tipo. Sanity checks obligatorios antes de seguir:
- `silencio_bot` (subtipo `sin_respuesta_final`) debería ser raro en B (< 3% de las que respondieron); si es > 10%, revisar si el último turno del usuario es un "gracias" post-cierre (no es bug) y agregar exclusión `RE_CIERRE = r'^(gracias|ok|vale|👍)'` al detector.
- `hora_no_monotona` alto (> 5%) significa que la agregación por HORA desordena turnos dentro de la misma hora: anotarlo como límite y NO usar `latencia_alta` como cifra dura.
- `pct_convs` se calcula sobre TODAS las conversaciones del bot, incluidas las que nunca respondieron. Para los tipos de contenido reportar además sobre `convs_con_respuesta`.

- [ ] **Step 5: Commit (solo resumen, nunca data/)**

```bash
git status --short bugs/   # verificar que data/ no aparece
git add bugs/run.py bugs/tests/test_run.py bugs/resumen.json
git commit -m "analisis(gabi): runner de detectores + resumen agregado por bot/etapa/ruteo"
```

---

### Task 6: Muestreo y validación manual (precisión por detector)

Los detectores de contenido son regex sobre lenguaje natural. **Ningún número de los tipos 1–5 va al informe sin esta validación.** Meta: precisión ≥ 80% con n=15 por tipo (se reporta como cifra); entre 60–80% se reporta como "indicio" con la precisión medida; < 60% se ajusta el regex y se re-valida, o se retira.

**Files:**
- Create: `bugs/muestra.py`
- Create: `bugs/precision.py`
- Create: `bugs/validacion.csv`

- [ ] **Step 1: Script de muestreo**

`bugs/muestra.py`:
```python
"""Imprime N conversaciones redactadas que tienen un hallazgo del tipo dado, marcando el turno que disparó.
Uso: python3 bugs/muestra.py <tipo> [n=15] [seed=7] [bot=A|B]"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse import parse_turns, redact  # noqa: E402

HERE = Path(__file__).resolve().parent
tipo = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 7)
bot = sys.argv[4] if len(sys.argv) > 4 else None

hall = [json.loads(l) for l in open(HERE / 'data' / 'hallazgos.jsonl')]
hall = [h for h in hall if h['tipo'] == tipo and (bot is None or h['bot'] == bot)]
por_deal = {}
for h in hall:
    por_deal.setdefault(h['deal_id'], []).append(h)
convs = {r['deal_id']: r for r in json.load(open(HERE / 'data' / 'convs.json'))}

print(f"# {tipo}: {len(hall)} hallazgos en {len(por_deal)} conversaciones. Muestra de {n}.")
print("# Marca cada deal en bugs/validacion.csv como TP (bug real) o FP (falso positivo).\n")
for deal in random.sample(sorted(por_deal), min(n, len(por_deal))):
    r = convs[deal]
    marcados = {h['idx']: h.get('subtipo') for h in por_deal[deal]}
    print('=' * 78)
    print(f"deal {deal} · bot {r['bot']} · {r['etapa_muerte']} · ruteado={int(r['agendo']) or int(r['inmo'])}")
    print('=' * 78)
    for t in parse_turns(r['c']):
        flag = f"  <<< {tipo}/{marcados[t.idx]}" if t.idx in marcados else ''
        hora = t.hora.strftime('%m-%d %H:%M') if t.hora else '?'
        print(f"[{hora}] {t.rol.upper()}:{flag}")
        for line in redact(t.texto).split('\n'):
            print(f"    {line}")
    print()
```

- [ ] **Step 2: Generar las muestras de los tipos de contenido (a `data/`, no se commitean)**

```bash
cd ~/habi/tableros-marketing-habi/analisis-gabi-completitud
for t in pregunta_ignorada ambigua_registrada repregunta_dato_ya_dado intencion_ignorada media_no_manejado nudge_anomalo silencio_bot; do
  python3 bugs/muestra.py $t 15 7 B > bugs/data/muestra_${t}_B.txt
done
python3 bugs/muestra.py pregunta_ignorada 10 7 A > bugs/data/muestra_pregunta_ignorada_A.txt
wc -l bugs/data/muestra_*.txt
```

- [ ] **Step 3: Leer las muestras y etiquetar**

Leer cada `bugs/data/muestra_*.txt` completo. Por cada deal, agregar una fila a `bugs/validacion.csv` con la cabecera:
```csv
tipo,bot,deal_id,veredicto,nota
```
`veredicto` ∈ {`TP`, `FP`}. En `nota` (≤ 80 chars, **sin copiar texto del usuario**) decir por qué es FP cuando lo es, p. ej. `pregunta retorica`, `gabi si respondio en el mismo turno`, `usuario dio el dato en otra unidad`. Criterio de TP por tipo:
- `pregunta_ignorada`: el usuario pidió información y Gabi en su siguiente turno no la dio ni la acusó.
- `ambigua_registrada`: un lector humano no puede saber qué valor quedó registrado y Gabi no pidió aclaración.
- `repregunta_dato_ya_dado`: el dato estaba escrito de forma inequívoca antes de la re-pregunta.
- `intencion_ignorada`: el usuario expresó opt-out/pedido claro y Gabi siguió el guion.
- `nudge_anomalo`: el usuario ya había contestado a lo último que Gabi pidió.

- [ ] **Step 4: Script de precisión**

`bugs/precision.py`:
```python
"""Precisión por tipo a partir de bugs/validacion.csv. Imprime una tabla markdown para el informe."""
import csv
from collections import defaultdict
from pathlib import Path

rows = list(csv.DictReader(open(Path(__file__).resolve().parent / 'validacion.csv')))
acc = defaultdict(lambda: {'TP': 0, 'FP': 0})
for r in rows:
    acc[(r['tipo'], r['bot'])][r['veredicto'].strip().upper()] += 1
print('| Tipo | Bot | n | TP | Precisión | Estatus |')
print('|---|---|---|---|---|---|')
for (tipo, bot), v in sorted(acc.items()):
    n = v['TP'] + v['FP']
    p = 100 * v['TP'] / n if n else 0
    estatus = 'cifra' if p >= 80 else 'indicio' if p >= 60 else 'retirar/ajustar'
    print(f'| {tipo} | {bot} | {n} | {v["TP"]} | {p:.0f}% | {estatus} |')
```

- [ ] **Step 5: Correr la precisión e iterar**

```bash
python3 bugs/precision.py
```
Para cada tipo con `retirar/ajustar`: leer las notas de FP, ajustar el regex correspondiente en `bugs/detectores.py`, agregar un test que reproduzca el falso positivo (copiando la estructura, no el texto real del usuario), correr `bugs/.venv/bin/pytest bugs/tests -q`, `python3 bugs/run.py`, re-muestrear con **otra semilla** (`seed=11`) y re-etiquetar. Máximo dos iteraciones por tipo; si sigue < 60%, se retira del informe y se anota en "Límites".

- [ ] **Step 6: Commit**

```bash
git add bugs/muestra.py bugs/precision.py bugs/validacion.csv bugs/detectores.py bugs/tests/test_detectores.py bugs/resumen.json
git commit -m "analisis(gabi): muestreo + validacion manual de detectores (precision por tipo)"
git push origin pool-ab-view
```

---

### Task 7 (opcional): Juez LLM para las categorías semánticas

Cuándo hacerla: si `pregunta_ignorada` o `ambigua_registrada` quedaron en "indicio" (60–80%), o para cubrir el bot A, donde el LLM libre siempre "responde algo" y el regex de guion no aplica (subtipo `candidata_llm`).

**Decisión previa de Nicolas (no del agente):** las conversaciones salen del entorno de Habi hacia el API de Anthropic. `redact()` quita nombre, teléfono y email pero **no** la dirección del inmueble. Si no hay OK explícito, esta tarea se salta y se dice en el informe.

**Files:**
- Create: `bugs/juez.py`
- Genera: `bugs/data/juez.jsonl` (ignorado), `bugs/juez_resumen.json` (commiteable)

- [ ] **Step 1: Verificar credenciales sin pedir claves**

```bash
ant auth status 2>/dev/null || echo "sin perfil ant"; python3 -c "import anthropic; print(anthropic.__version__)"
```
Si no hay perfil ni `ANTHROPIC_API_KEY`, sugerir `ant auth login` y parar aquí. Si falta el paquete: `pip install anthropic`.

- [ ] **Step 2: Implementar el juez**

`bugs/juez.py`:
```python
"""Juez LLM: para una muestra de conversaciones redactadas, responde si hubo pregunta sin respuesta,
respuesta ambigua ignorada u otra falla del agente. Uso: python3 bugs/juez.py [n=200] [seed=7]
Escribe bugs/data/juez.jsonl (por deal) y bugs/juez_resumen.json (agregado)."""
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse import parse_turns, redact  # noqa: E402

HERE = Path(__file__).resolve().parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 7)

SYSTEM = """Eres auditor de calidad de un chatbot inmobiliario (Gabi, Habi México) que recopila datos de un inmueble
por WhatsApp. Recibes una conversación transcrita (turnos GABI/USUARIO). Evalúa SOLO el comportamiento del bot.
Devuelve únicamente un JSON con esta forma exacta, sin texto adicional:
{"pregunta_sin_respuesta": true|false, "pregunta_texto": "cita corta o null",
 "ambigua_ignorada": true|false, "ambigua_texto": "cita corta o null",
 "otras_fallas": ["descripcion breve", ...], "gravedad": "ninguna|leve|media|grave", "explicacion": "1-2 frases"}
Reglas: pregunta_sin_respuesta = el usuario pidió información (precio, tiempos, proceso, quién es Habi, etc.) y el bot
en su siguiente turno no la contestó ni acusó recibo. ambigua_ignorada = el usuario dio una respuesta que un humano
no podría registrar sin aclarar (\"no sé\", \"como 100\", \"3 y un estudio\", sin número donde se pedía número) y el bot
la dio por registrada. No cuentes como falla que el bot siga el guion cuando el usuario respondió bien."""


def render(c):
    return '\n'.join(f"{t.rol.upper()}: {redact(t.texto)}" for t in parse_turns(c))


def juzgar(client, conv_txt):
    resp = client.beta.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        system=SYSTEM,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": conv_txt}],
    )
    if resp.stop_reason == "refusal":
        return {"error": "refusal"}
    texto = ''.join(b.text for b in resp.content if b.type == "text")
    m = re.search(r'\{[\s\S]*\}', texto)
    try:
        return json.loads(m.group(0)) if m else {"error": "sin_json", "raw": texto[:300]}
    except json.JSONDecodeError:
        return {"error": "json_invalido", "raw": texto[:300]}


def main():
    rows = [r for r in json.load(open(HERE / 'data' / 'convs.json')) if re.search(r'(?m)^Usuario:', r['c'])]
    muestra = random.sample(rows, min(N, len(rows)))
    client = anthropic.Anthropic()
    out = open(HERE / 'data' / 'juez.jsonl', 'w')
    res = []
    for i, r in enumerate(muestra, 1):
        j = juzgar(client, render(r['c']))
        rec = {'deal_id': r['deal_id'], 'bot': r['bot'], 'etapa_muerte': r['etapa_muerte'], **j}
        out.write(json.dumps(rec, ensure_ascii=False) + '\n'); out.flush()
        res.append(rec)
        if i % 20 == 0:
            print(f'{i}/{len(muestra)}', file=sys.stderr)
    ok = [x for x in res if 'error' not in x]
    resumen = {
        'n': len(res), 'errores': len(res) - len(ok),
        'por_bot': dict(Counter(x['bot'] for x in ok)),
        'pregunta_sin_respuesta': dict(Counter(x['bot'] for x in ok if x.get('pregunta_sin_respuesta'))),
        'ambigua_ignorada': dict(Counter(x['bot'] for x in ok if x.get('ambigua_ignorada'))),
        'gravedad': dict(Counter(x.get('gravedad') for x in ok)),
        'otras_fallas_top': Counter(f.lower()[:60] for x in ok for f in x.get('otras_fallas', [])).most_common(15),
    }
    json.dump(resumen, open(HERE / 'juez_resumen.json', 'w'), ensure_ascii=False, indent=2)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
```
Nota: el parámetro `fallbacks="default"` (beta `server-side-fallback-2026-07-01`) re-ejecuta en otro modelo si el clasificador de seguridad declina la petición; es la recomendación por defecto para `claude-opus-5`. Si molesta, quitar las dos líneas y usar `client.messages.create`.

- [ ] **Step 3: Prueba con 5 conversaciones y luego la muestra completa**

```bash
python3 bugs/juez.py 5 && cat bugs/juez_resumen.json
```
Expected: 5 registros sin `error`, JSON bien formado. Luego:
```bash
python3 bugs/juez.py 200 7
```
Costo estimado: 200 conversaciones × ~1.500 tokens ≈ 0,3 M tokens de entrada ≈ US$ 2–3 con `claude-opus-5`.

- [ ] **Step 4: Cruzar juez vs regex sobre los mismos deals**

```bash
python3 - <<'EOF'
import json
from pathlib import Path
j = {x['deal_id']: x for x in map(json.loads, open('bugs/data/juez.jsonl')) if 'error' not in x}
h = {}
for l in open('bugs/data/hallazgos.jsonl'):
    x = json.loads(l); h.setdefault(x['deal_id'], set()).add(x['tipo'])
for tipo, campo in [('pregunta_ignorada', 'pregunta_sin_respuesta'), ('ambigua_registrada', 'ambigua_ignorada')]:
    tp = sum(1 for d in j if j[d].get(campo) and tipo in h.get(d, ()))
    fn = sum(1 for d in j if j[d].get(campo) and tipo not in h.get(d, ()))
    fp = sum(1 for d in j if not j[d].get(campo) and tipo in h.get(d, ()))
    print(f'{tipo}: regex∧juez={tp}  solo juez (regex se lo pierde)={fn}  solo regex (juez dice no)={fp}')
EOF
```
El "solo juez" es la estimación de **recall** perdido por el regex: va al informe como rango (cifra regex = piso; regex + solo-juez extrapolado = techo).

- [ ] **Step 5: Commit**

```bash
git add bugs/juez.py bugs/juez_resumen.json
git commit -m "analisis(gabi): juez LLM sobre muestra redactada (recall de pregunta/ambiguedad ignoradas)"
```

---

### Task 8: Informe `BUGS-AGENTE.md` y cierre

**Files:**
- Create: `BUGS-AGENTE.md`
- Modify: `PROMPT-SESION.md` (sección HILOS ABIERTOS)

- [ ] **Step 1: Escribir el informe con esta estructura exacta**

`BUGS-AGENTE.md`:
```markdown
# Bugs y fallas del agente Gabi (MX)

**Fecha:** 2026-09-__ · **Ventana:** conversaciones jun–ago 2026 (misma cohorte que `OPORTUNIDADES.md`)
**Fuente:** `sellers-main-prod.chatbots.mabi_mx` vía `queries/export_conversaciones.sql` · **Cohorte:** bot B = N deals, bot A = N deals (N con al menos una respuesta del usuario)
**Método:** detectores regex sobre turnos (`bugs/detectores.py`), validados a mano (`bugs/validacion.csv`, precisión por tipo abajo); juez LLM sobre muestra de N (si se hizo Task 7).

## 1. Resumen ejecutivo
(3–5 bullets: los 3 tipos con más volumen validado, el que más se concentra en una etapa de muerte, y el bug técnico más claro. Cada cifra con su precisión.)

## 2. Tabla de fallas
| Tipo | Bot | Convs afectadas | % de las que respondieron | Precisión (n) | Estatus |
(una fila por tipo × bot, de `bugs/resumen.json` + `python3 bugs/precision.py`)

## 3. Detalle por tipo
### 3.x <tipo>
- Qué detecta y cómo (una línea, referencia al detector).
- Volumen y subtipos.
- Un ejemplo redactado (turnos relevantes, con `[nombre]`/`[tel]`, sin dirección textual).
- Dónde se concentra (etapa de muerte) y ruteo con bug vs sin bug (correlación, no causa).
- Fix sugerido (una línea, en términos del guion o del flujo).

## 4. Cruce con el funnel de completitud
(Cómo se reparten los bugs por etapa de muerte de §1 de OPORTUNIDADES.md. ¿Los 486 loops de dirección tienen `loop_repeticion`/`repregunta`? ¿Cuántas muertes en dirección vienen precedidas de `media_no_manejado` o `pregunta_ignorada`? Conecta con las oportunidades #1, #3, #4 y #5.)

## 5. Bugs técnicos
(plantilla_rota, duplicado_gabi, latencia, hora_no_monotona: conteos y ejemplos. Si `hora_no_monotona` es alto, decir que latencia es indicativa.)

## 6. Límites
- Regex sobre texto de LLM: precisión medida en §2; recall estimado con el juez (o "no estimado").
- Adjuntos/ubicación: qué rastro dejan en `messages` (o que no dejan).
- `latencia_alta` depende de que HORA sea el envío real.
- Correlación bug ↔ ruteo no es causal (auto-selección, ver OPORTUNIDADES.md §5).

## 7. Reproducibilidad
1. `bq query ... < queries/export_conversaciones.sql > bugs/data/convs.json`
2. `bugs/.venv/bin/pytest bugs/tests -q && python3 bugs/run.py`
3. `python3 bugs/muestra.py <tipo> 15 7 B` · `python3 bugs/precision.py`
4. (opcional) `python3 bugs/juez.py 200 7`
```
Rellenar TODAS las secciones con los números de `bugs/resumen.json` y `bugs/precision.py`. Ningún número de los tipos 1–5 sin su precisión al lado. Ejemplos: copiar de las muestras ya redactadas y además reemplazar calles/números por `[dirección]`.

- [ ] **Step 2: Agregar el hilo a `PROMPT-SESION.md`**

En la lista `HILOS ABIERTOS`, agregar como punto 4:
```
4. Bugs del agente: BUGS-AGENTE.md tiene la tabla validada (bugs/detectores.py + bugs/validacion.csv).
   Siguiente: priorizar con producto los tipos de mayor volumen × precisión y re-correr tras cada
   cambio de guion (python3 bugs/run.py) para medir si bajan.
```

- [ ] **Step 3: Tests verdes y commit final**

```bash
cd ~/habi/tableros-marketing-habi/analisis-gabi-completitud
bugs/.venv/bin/pytest bugs/tests -q
git status --short bugs/    # data/ NO debe aparecer
git add BUGS-AGENTE.md PROMPT-SESION.md
git commit -m "analisis(gabi): informe de bugs y fallas del agente (detectores validados + cruce con funnel)"
git pull --rebase && git push origin pool-ab-view
```

---

## Criterios de terminado

- `bugs/.venv/bin/pytest bugs/tests -q` verde.
- `bugs/data/` nunca entró a git (`git log --all -- analisis-gabi-completitud/bugs/data` vacío).
- Cada tipo reportado en `BUGS-AGENTE.md` tiene: conteo, % sobre conversaciones con respuesta, precisión medida y un ejemplo redactado.
- El cruce con etapa de muerte conecta al menos con las oportunidades #1 (dirección) y #4/#5 (re-pregunta y nudge) de `OPORTUNIDADES.md`.
- Toda cifra tiene su query o script reproducible en `queries/` o `bugs/`.
