# Ventanas · tabla de control — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Debajo de las tres cards de Ventanas del panel, mostrar la tabla de control (bloques 1–3), la franja de salud del agente (bloque 4), la mini-tabla semanal y las gráficas de volumen y calidad, con el bloque 1 de hoy y el bloque 4 refrescados en vivo.

**Architecture:** Un módulo Python nuevo `marketing-loop/ventanas_control.py` con dos capas: extracción (SQL sobre Neon, devuelve filas planas con fecha local) y agregación pura (ruta, cohorte, madurez, referencia) con tests sin base. `build_data.py` lo llama y escribe `ventanas.control` en `data.json`. Un endpoint `GET /api/ventanas/control-hoy` en el repo marketing-loop-sellers (rama del agente) sirve HOY del bloque 1 y el bloque 4. `index.html` pinta desde `data.json` y sobreescribe con el vivo.

**Tech Stack:** Python 3.12 (psycopg vía `sources_neon._rows`), pytest, Chart.js 4 (ya cargado), FastAPI (repo del agente).

Spec: `docs/superpowers/specs/2026-09-07-ventanas-tabla-control-design.md`.

---

## Estructura de archivos

- Create `marketing-loop/ventanas_control.py` — constantes (rutas, plantillas, acciones), `ruta()`, `construir()` (puro), `extraer()` (SQL), `bloque4()` (SQL), `control()` (orquesta).
- Create `marketing-loop/tests/test_ventanas_control.py` — tests de la capa pura.
- Modify `marketing-loop/build_data.py:832` — `"ventanas": {..., "control": ventanas_control.control(co["plantillas"], M)}`.
- Modify `marketing-loop/index.html` — `renderVentanasControl()` + CSS, llamado al final de `renderVentanasPanel()`; `MET_HELP` con las 27 métricas.
- Create (repo marketing-loop-sellers) `plantillas/envio.py` — `GET /api/ventanas/control-hoy`; `tests/test_tablero_contract.py` — test de forma.

## Interfaces (fijas para todas las tareas)

```python
RUTAS = ("compra_directa", "tibio", "nocontesta")
PRIMER_ENVIO = {"ventanas_nocontesta_co_v1", "ventanas_compra_co_v1", "ventanas_tibio_co_v1"}
SEGUIMIENTO  = {"ventanas_reenganche_co_v1"}
FALLA  = {"SIN_DIRECCION", "NO_TEMPLATE", "SEND_FAIL", "BAD_PHONE", "TEMPLATE_NO_VENTANAS"}
GUARDA = {"TERMINAL", "CAP_DIARIO", "FUERA_HORARIO", "DEDUP", "PROGRAMA_AJENO"}

def ruta(flujo, kind, gestion) -> str
def es_habil(fecha_iso) -> bool                      # lunes-viernes
def madura(fecha_iso, hoy_iso) -> bool               # (hoy - fecha) >= 4 días
def mediana(valores) -> float | None
def construir(raw, hoy_iso, ahora_hhmm) -> dict      # PURO → ventanas.control sin "agente"
```

`raw` (todo con fechas ya en Bogotá, como texto `YYYY-MM-DD`):
```
raw = {
 "hs":   [{"phone","fecha","hora":"HH:MM","ts": iso, "action","flujo","kind","gestion","template"}],  # sin DRY
 "env":  [{"phone","fecha","template","accepted": bool,"message_id"}],                                # template ventanas%
 "resp": set(phone),           # agent_thread user ∪ contact_status.responded_at
 "consent": set(phone), "completa": set(phone),
 "deal_ok": {phone: step_is_null(bool)}, "deal_fallo": {phone: [http_code]},
 "handoff": {phone: motivo}, "optout": set(phone), "lead_fired": {phone: iso_ts},
 "delivered": set(message_id), "plantillas": [{"nombre","estado"}],
}
```

Salida `construir(...)`:
```
{"generado", "rutas", "dias": [{fecha, habil, madura, hoy, todas:{B1,B2,B3}, compra_directa:{...}, tibio:{...}, nocontesta:{...}}],
 "semanas": [{semana, todas:{primer_envio, entregados}, <ruta>:{...}}],
 "plantillas": [{nombre, estado, aprobada}], "referencia": {todas:{col: mediana}, <ruta>:{...}}}
B1 = {posts, personas, nuevas, dedup_pct, bloqueos:{action:n}, ultimo_post}
B2 = {primer_envio, seguimientos, rechazos}
B3 = {cohorte, recuperados, respondieron, consintieron, entrevista_completa, deal_completo, deal_parcial,
      deal_fallo, deal_fallo_codes, handoff_sin_respuesta, handoff_pide_llamada, optout, conversion_total, horas_a_deal}
```
Días: desde el primer POST (19-ago) hasta hoy, todos los calendario (fin de semana `habil:false`); el front muestra los últimos 20 hábiles.
Referencia: por columna en {posts, personas, nuevas, cohorte, primer_envio, respondieron, consintieron, entrevista_completa, deal_completo, conversion_total}, mediana de los últimos 7 días hábiles **maduros** con `cohorte >= 5` para las de %.

---

### Task 1: ruta, calendario y mediana (puro)
**Files:** Create `marketing-loop/ventanas_control.py`, `marketing-loop/tests/test_ventanas_control.py`.
- [ ] Tests: `ruta('compra_wa','llamada','NO CONTACTABLE 3')=='compra_directa'`; `ruta(None,'whatsapp',None)=='tibio'`; `ruta(None,None,'Contactar por WhatsApp')=='tibio'`; `ruta(None,'llamada','NO CONTACTABLE 3')=='nocontesta'`; `ruta(None,None,None)=='nocontesta'`. `es_habil('2026-09-05') is False`, `('2026-09-04') is True`. `madura('2026-09-03','2026-09-07') is True`, `('2026-09-04','2026-09-07') is False`. `mediana([])==None`, `mediana([1,5,3])==3`, `mediana([1,2,3,4])==2.5`.
- [ ] Correr: `cd marketing-loop && ../../marketing-loop-sellers/.venv/bin/python -m pytest tests/test_ventanas_control.py -q` → falla por import.
- [ ] Implementar. Correr → pasa. Commit `ventanas_control: ruta, calendario y mediana`.

### Task 2: construir() — bloques 1, 2 y 3 por día y ruta
**Files:** Modify `ventanas_control.py`, tests.
- [ ] Fixture: 3 días (jue 03, vie 04, lun 07 = hoy) con: A (compra_wa, POST 03 SENT compra, envío 03, respondió, consent, completa, deal_ok step null, lead_fired 04 10:00) · B (nocontesta, POST 03 SENT, POST 03 DEDUP, envío 03, optout) · C (nocontesta, RECUPERADO 04, envío 04 nocontesta, deal_ok step no null) · D (whatsapp, POST 04 SIN_DIRECCION) · E (compra_wa, POST 07 SENT, reenganche 07, deal_fallo 500) · F (POST 04 SENT en ruta nocontesta, sin más).
- [ ] Asserts (día 03, todas): posts 3, personas 2, nuevas 2, dedup_pct 33.3, ultimo_post '09:30' (max), bloqueos {'DEDUP':1}; B2 primer_envio 2, seguimientos 0, rechazos 0; B3 cohorte 2, recuperados 0, respondieron 1, consintieron 1, entrevista_completa 1, deal_completo 1, deal_parcial 0, optout 1, horas_a_deal ≈ 24.5, conversion_total 50.0 (madura). Día 04 todas: posts 2 (D y F; C es RECUPERADO y no cuenta), cohorte 3 (C, D, F), recuperados 1, deal_parcial 1, conversion_total None (inmadura). Día 07 (hoy): `hoy:True`, seguimientos 1, deal_fallo 1 y codes ['500']. Ruta `compra_directa` día 03: cohorte 1, deal_completo 1. Día 05/06: `habil:False`, posts 0.
- [ ] Implementar `construir` (sin semanas/referencia todavía: devolverlas vacías). Correr → pasa. Commit.

### Task 3: semanas, plantillas y referencia
- [ ] Tests: `semanas` agrupa por ISO (`2026-W36`), `primer_envio` cuenta `accepted` y `entregados` cuenta message_id ∈ delivered; `plantillas` → `aprobada = estado=='APPROVED'`; `referencia['todas']['posts']` = mediana de los últimos 7 hábiles maduros (fixture con 10 días donde el hoy y ayer NO entran); `conversion_total` ignora cohortes con `cohorte<5`.
- [ ] Implementar. Correr todo `tests/` → pasa. Commit.

### Task 4: extracción SQL e integración en el build
**Files:** Modify `ventanas_control.py` (`extraer(N)`, `bloque4(N)`, `control(plantillas, M)`), `build_data.py:832`.
- [ ] `extraer`: 9 consultas (hs sin `DRY:%` con `received_at AT TIME ZONE 'America/Bogota'`; send_log `template LIKE 'ventanas%%'`; responders = `agent_thread campaign='ventanas' role='user'` ∪ `contact_status responded_at IS NOT NULL` cuyo último envío aceptado es ventanas; intake consent/completa/lead_fired; backbone_intento con `resultado` y join a intake.step; dapta; optout `action_taken='CLOSE_OPT_OUT'`). `delivered` = `{mid for mid,v in M.mart_by_msgid(90,'CO').items() if v.get('status')=='delivered'}`.
- [ ] `bloque4`: por día — atascadas (window `lag(content)` ×2 seguidas = 3 iguales), latencia (`percentile_cont(0.5)` de `ts - lag(ts)` cuando el anterior es `role='user'`, por teléfono), errores (`TURN_ERROR`,`LLM_ERROR`); abiertas = snapshot (consent AND step NOT NULL AND last_inbound_at > now()-72h AND lead_fired_at IS NULL) puesto en el día de hoy.
- [ ] `control()` envuelve en try/except → `{"error": str(e), "generado": ...}`.
- [ ] Integrar en `build_data.py`; rebuild con el `.env` del loop; verificar contra Neon: `dias` del 03-sep `todas.b1.posts == 294`, cohorte por ruta suma 265/61/652 en total (más recuperados). Commit + push (rebase primero).

### Task 5: endpoint en vivo (repo marketing-loop-sellers, rama `feat/whatsapp-sdr-agent`)
**Files:** Modify `plantillas/envio.py` (junto a `/api/ventanas/alertas`), `tests/test_tablero_contract.py`.
- [ ] Test de contrato: `GET /api/ventanas/control-hoy?token=` → `{fecha, hora, b1:{todas,compra_directa,tibio,nocontesta: {posts,personas,nuevas,dedup_pct,bloqueos,ultimo_post}}, agente:{atascadas,abiertas,latencia_s,errores}}` con el doble de `conn` del test de alertas. Correr → falla 404.
- [ ] Implementar con la MISMA SQL de bloque 1 (HOY) y bloque 4 del módulo (duplicada a propósito, comentario cruzado con el hash del commit del tablero). `_auth(token)`, `_cors`. Correr tests → pasa. Commit, push (Vercel despliega la rama). Verificar `curl` con token → 200 y shape.

### Task 6: front
**Files:** Modify `marketing-loop/index.html`.
- [ ] CSS: `.ctrl-wrap` (scroll-x), `.ctrl th.grp`, `.c-rojo`, `.c-gris`, `.c-finde`, `.c-ref` (fila fija al pie), `.salud` (5 KPIs), `.mini-sem`.
- [ ] JS: `ventRuta='todas'`; `setVentRuta(r)`; `renderVentanasControl()` llamado al final de `renderVentanasPanel()` (CO). Reglas de rojo en JS: `<30%` de `referencia[ruta][col]` salvo `hoy`; fallas >0; silencio (hábil sin POST; hoy además `ahora>=10:00` solo con dato vivo); optout > 5% de respondieron; latencia >60 s; plantilla no aprobada. `MET_HELP` con el texto "Cálculo" de cada fila del spec.
- [ ] Tabla: últimos 20 días hábiles + findes atenuados, más reciente arriba; grupos B1 · B2 · B3; % bajo 11–14; fila referencia al pie.
- [ ] Franja bloque 4 + mini-tabla semanal (primer envío, entregados, % entrega; estado de plantillas).
- [ ] Gráfica volumen: barras apiladas (3 rutas + gris recuperados). Gráfica calidad: líneas de `conversion_total` por ruta, solo maduras, eje %. Paleta por ruta validada con `validate_palette.js` claro/oscuro; re-render en `applyTheme`.
- [ ] Vivo: si hay token, `fetch(API_BASE+'/api/ventanas/control-hoy?token=')` → sobreescribe fila de hoy (B1) y franja; etiqueta "en vivo HH:MM". Sin token o error: dato del build con su hora.
- [ ] `node --check` del JS; capturas headless claro (ruta todas) y oscuro (ruta compra_directa); commit; rebase; push; confirmar Pages `built`.
