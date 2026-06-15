# Diagnóstico y proyección de performance CO 2026 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir un informe HTML narrativo que diagnostique por fuente de performance (WEB, Lead Forms, Habímetro) por qué CO no cumple metas en la temporada del Mundial 2026, y proyecte Q2+Q3 en escenarios optimista y conservador.

**Architecture:** Pipeline estándar de `tableros-marketing`: `query_*.sql` (BigQuery) → `build_data.py` (ensambla + modela escenarios) → `data.json` → `index.html` autocontenido con Chart.js. Atribución de inversión por UTM (diccionario `registro_unico_utm_mkt_colombia`); registros/asignados/CVR por `fuente` de `tabla_inmuebles_general`; ambos ejes reconcilian por etiqueta (WEB / lead_forms / Estudio Inmueble). Metas desde `okr-marketing/data.json`.

**Tech Stack:** BigQuery (bq CLI), Python 3 stdlib (csv/json), Chart.js, HTML/CSS estático (GitHub Pages).

**Marco causal (espina del informe):** `Asignados = Inversión × (1/CPL) × CVR(registro→asignado)`. Tres palancas separables: inversión, eficiencia de captación (CPL/CPM/CPC), conversión (Backbone −16%), + demanda transversal (mundial/festivos).

**Validación (en vez de unit tests):** cada tarea de datos cierra con un chequeo de reconciliación contra una fuente independiente (OKR, match-rate UTM, tesis del −16%). Eso es la disciplina equivalente al TDD aquí.

**Convención `fuente` (las 3 de performance, fuente_id):** `WEB`=3, `Estudio Inmueble`(Habímetro)=20, `lead_forms`=39. (Resto: CRM/Broker/comercial = contexto, no se grafican costos.)

---

## File Structure

- `tableros-marketing/diagnostico-performance-co/` (nueva carpeta)
  - `query_inversion_utm.sql` — spend/impr/clicks por fuente×día, atribuido por UTM. Semanal + diario.
  - `query_funnel.sql` — registros, asignados, CVR por fuente×día (cohort). Semanal + diario.
  - `build_data.py` — lee los 2 JSON de BQ + `okr-marketing/data.json`, ensambla `data.json`, calcula CPL/CPM/CPC, varas (original/recalibrada/YoY) y los escenarios de proyección.
  - `data.json` — salida consumida por el HTML.
  - `index.html` — informe autocontenido (5 capítulos + resumen).
  - `meta.json` — registro en el hub.
  - `hitos.json` — anotaciones de hitos fechados (mundial, vueltas electorales, festivos), editable a mano.

---

## Task 1: Scaffold + query de inversión atribuida por UTM

**Files:**
- Create: `diagnostico-performance-co/query_inversion_utm.sql`

- [ ] **Step 1: Crear carpeta y la query**

```bash
mkdir -p /home/administrador/habi/tableros-marketing/diagnostico-performance-co
```

`query_inversion_utm.sql`:
```sql
-- Inversión de performance CO atribuida por UTM (diccionario registro_unico_utm).
-- Match validado 2026-06-15: 100% del spend cruza por campana_original.
-- Granularidad diaria; el build agrega a semana ISO. Solo fuentes Paid de performance.
WITH dict AS (
  SELECT DISTINCT campana_mercadeo_original, mkt_channel_big, mkt_media
  FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
)
SELECT
  CAST(i.date AS STRING) AS dt,
  d.mkt_channel_big       AS fuente,   -- WEB | lead_forms | Estudio Inmueble
  ROUND(SUM(i.spend))       AS spend,
  ROUND(SUM(i.impressions)) AS impr,
  ROUND(SUM(i.clicks))      AS clicks
FROM `papyrus-data.habi_wh_bi.resumen_inversiones_mkt_co` i
LEFT JOIN dict d ON i.campana_original = d.campana_mercadeo_original
WHERE i.date >= '2025-01-01'
  AND i.date < CURRENT_DATE()
  AND d.mkt_media = 'Paid'
  AND d.mkt_channel_big IN ('WEB','lead_forms','Estudio Inmueble')
GROUP BY 1, 2
ORDER BY 1, 2
```

- [ ] **Step 2: Ejecutar y guardar salida**

```bash
cd /home/administrador/habi/tableros-marketing/diagnostico-performance-co
bq query --use_legacy_sql=false --format=prettyjson --max_rows=100000 \
  "$(cat query_inversion_utm.sql)" > _inversion.json
```
Expected: JSON array con filas `{dt, fuente, spend, impr, clicks}` desde 2025-01-01.

- [ ] **Step 3: Validar reconciliación contra OKR**

```bash
python3 -c "
import json
rows=json.load(open('_inversion.json'))
tot=sum(float(r['spend']) for r in rows if r['dt']>='2026-01-01')
print('spend perfo 2026 (USD):', round(tot))
"
```
Expected: el total 2026 debe quedar **por debajo pero cercano** al `invest.actual` anual del OKR CO (577.523, que incluye además fuentes no-performance). Si el número es mayor que el OKR o ~0, el join falló — revisar.

- [ ] **Step 4: Commit**

```bash
cd /home/administrador/habi/tableros-marketing
git add diagnostico-performance-co/query_inversion_utm.sql
git commit -m "diagnostico-performance-co: query inversión atribuida por UTM"
```

---

## Task 2: Query de funnel — registros, asignados, CVR por fuente

**Files:**
- Create: `diagnostico-performance-co/query_funnel.sql`

- [ ] **Step 1: Escribir la query** (cohort por `fecha_creacion`, lógica lifteada de `queries/funnel_registros.sql`)

```sql
-- Registros, asignados y CVR(registro->asignado) por fuente de performance CO.
-- Cohort: agrupa por fecha_creacion; asg = el nid llegó EN ALGÚN MOMENTO a Primer_asigancion.
-- Diario; el build agrega a semana ISO. Historia completa desde 2025-01-01.
WITH funnel_reach AS (
  SELECT nid, MIN(IF(valor='Primer_asigancion', DATE(fecha), NULL)) AS asg_date
  FROM `papyrus-data.habi_wh_bi.funnel_diarios_col`
  WHERE nid IS NOT NULL
  GROUP BY nid
),
base AS (
  SELECT tig.nid, tig.fuente, DATE(tig.fecha_creacion) AS fecha, fr.asg_date
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` tig
  LEFT JOIN funnel_reach fr ON fr.nid = tig.nid
  WHERE tig.fecha_creacion IS NOT NULL
    AND DATE(tig.fecha_creacion) >= '2025-01-01'
    AND DATE(tig.fecha_creacion) < CURRENT_DATE()
    AND tig.fuente IN ('WEB','lead_forms','Estudio Inmueble')
)
SELECT
  CAST(fecha AS STRING) AS dt,
  fuente,
  COUNT(DISTINCT nid) AS registros,
  COUNT(DISTINCT IF(asg_date IS NOT NULL, nid, NULL)) AS asignados
FROM base
GROUP BY 1, 2
ORDER BY 1, 2
```

- [ ] **Step 2: Ejecutar y guardar**

```bash
cd /home/administrador/habi/tableros-marketing/diagnostico-performance-co
bq query --use_legacy_sql=false --format=prettyjson --max_rows=100000 \
  "$(cat query_funnel.sql)" > _funnel.json
```
Expected: filas `{dt, fuente, registros, asignados}`.

- [ ] **Step 3: Validar la tesis del −16% (CVR cae post-Backbone 12-mar)**

```bash
python3 -c "
import json
from collections import defaultdict
rows=json.load(open('_funnel.json'))
def cvr(lo,hi):
    r=a=0
    for x in rows:
        if lo<=x['dt']<hi:
            r+=x['registros']; a+=x['asignados']
    return a/r if r else 0
print('CVR pre-Backbone  (feb):', round(cvr('2026-02-01','2026-03-01')*100,1),'%')
print('CVR post-Backbone (may):', round(cvr('2026-05-01','2026-06-01')*100,1),'%')
"
```
Expected: el CVR de mayo debe estar varios puntos por debajo del de febrero (la tesis del doc de abril). Documentar el delta real.

- [ ] **Step 4: Commit**

```bash
cd /home/administrador/habi/tableros-marketing
git add diagnostico-performance-co/query_funnel.sql
git commit -m "diagnostico-performance-co: query funnel registros/asignados/CVR por fuente"
```

---

## Task 3: Extraer metas + actual oficial desde el OKR (las 3 varas)

**Files:**
- Create: `diagnostico-performance-co/_metas.json` (derivado, no se commitea como fuente)

- [ ] **Step 1: Derivar metas semanales por fuente desde el OKR**

`okr-marketing/data.json` ya trae `CO.tables.weeks[]` con `{label, leads:{meta,actual,prev}, invest}`. Pero a nivel TOTAL, no por fuente. Las series por fuente viven en `CO.tables` solo a nivel anual/quarter/month/week TOTAL; **el detalle por fuente está en el CSV fuente del sheet**. Verificar primero qué granularidad por fuente expone el data.json:

```bash
python3 -c "
import json
d=json.load(open('/home/administrador/habi/tableros-marketing/okr-marketing/data.json'))
co=d['CO']; print('sources:', co['sources'])
print('weeks keys:', list(co['tables']['weeks'][0].keys()))
print('ejemplo week:', co['tables']['weeks'][-1])
"
```
Expected: confirma si `weeks[]` trae desglose por fuente o solo TOTAL.

- [ ] **Step 2: Decisión de fuente de metas**

- Si el OKR data.json trae metas por fuente semanal → consumirlo directo en `build_data.py`.
- Si solo trae TOTAL → re-exportar el CSV `Cumplimiento Fuentes` del sheet (mismo que usa `okr-marketing/build_data.py`, ver su firma `<co_csv>`) y parsearlo con la misma lógica de `parse_sheet()` (offsets por fuente). Reusar esa función, no reescribirla.

- [ ] **Step 3: Calcular la vara recalibrada −16%**

La meta recalibrada = meta original × 0.84 (el −16% del doc de abril), aplicada desde la semana post-Backbone. Documentar en el build que el factor 0.84 viene de *Análisis de asignados de marketing — Colombia 2026* y es ajustable por fuente (Habímetro −27% según el doc; WEB/Lead Forms proporcional). Dejar los factores por fuente como constante nombrada al inicio de `build_data.py`:

```python
# Factor de recalibración post-Backbone por fuente (doc asignados CO abr-2026).
RECAL = {'WEB': 0.84, 'lead_forms': 0.84, 'Estudio Inmueble': 0.73}  # Habímetro -27%
```

- [ ] **Step 4: Commit** (solo si se agregó algún archivo derivado de apoyo; si no, saltar)

---

## Task 4: Correr el diagnóstico y fechar los hitos

**Files:**
- Create: `diagnostico-performance-co/hitos.json`
- Create: `diagnostico-performance-co/FINDINGS.md` (bitácora de hallazgos para redactar el HTML)

- [ ] **Step 1: Verificar fechas de hitos contra calendario y datos**

Anclar (verificar con WebSearch al ejecutar; no inventar):
- Mundial 2026: arranque 11-jun-2026.
- Elecciones presidenciales CO 2026: 1ª vuelta y 2ª vuelta (verificar fechas exactas).
- Lunes festivos CO de mayo–junio 2026 (Ley Emiliani): verificar fechas exactas.

Escribir `hitos.json`:
```json
[
  {"date":"2026-06-11","label":"Arranca Mundial 2026","tipo":"mundial"},
  {"date":"YYYY-MM-DD","label":"1ª vuelta presidencial","tipo":"eleccion"},
  {"date":"YYYY-MM-DD","label":"2ª vuelta presidencial","tipo":"eleccion"},
  {"date":"YYYY-MM-DD","label":"Festivo (Ley Emiliani)","tipo":"festivo"}
]
```

- [ ] **Step 2: Calcular CPM/CPC/CPL semanales y detectar saltos**

```bash
cd /home/administrador/habi/tableros-marketing/diagnostico-performance-co
python3 -c "
import json
from collections import defaultdict
inv=json.load(open('_inversion.json')); fun=json.load(open('_funnel.json'))
import datetime
def wk(dt): return datetime.date.fromisoformat(dt).isocalendar()[:2]
S=defaultdict(lambda:defaultdict(float))
for r in inv:
    if r['dt']<'2026-04-01': continue
    k=(wk(r['dt']),r['fuente'])
    S[k]['spend']+=float(r['spend']); S[k]['impr']+=float(r['impr']); S[k]['clicks']+=float(r['clicks'])
R=defaultdict(int)
for r in fun:
    if r['dt']<'2026-04-01': continue
    R[(wk(r['dt']),r['fuente'])]+=r['registros']
for k in sorted(S):
    s=S[k]; reg=R.get(k,0)
    cpm=s['spend']/s['impr']*1000 if s['impr'] else 0
    cpc=s['spend']/s['clicks'] if s['clicks'] else 0
    cpl=s['spend']/reg if reg else 0
    print(k, 'CPM',round(cpm,2),'CPC',round(cpc,2),'CPL',round(cpl,1),'reg',reg)
"
```
Expected: tabla semanal por fuente. Identificar las semanas donde CPM/CPC saltan y cruzarlas con `hitos.json` (ventana electoral). Anotar en `FINDINGS.md`.

- [ ] **Step 3: Escribir `FINDINGS.md`** con los números reales por palanca y fuente:
  - Gap de asignados Q2 vs cada vara (original / recalibrada / YoY).
  - Descomposición: cuánto del gap es CVR (Backbone), cuánto CPL (elecciones), cuánto demanda (mundial/festivos).
  - Hitos diarios desde 1-may con su explicación (qué pasó cada día notable).

- [ ] **Step 4: Commit**

```bash
cd /home/administrador/habi/tableros-marketing
git add diagnostico-performance-co/hitos.json diagnostico-performance-co/FINDINGS.md
git commit -m "diagnostico-performance-co: hitos fechados + bitácora de hallazgos"
```

---

## Task 5: build_data.py — ensamblar data.json + escenarios de proyección

**Files:**
- Create: `diagnostico-performance-co/build_data.py`

- [ ] **Step 1: Escribir el ensamblador**

`build_data.py` lee `_inversion.json`, `_funnel.json`, `okr-marketing/data.json`, `hitos.json`; produce `data.json` con, por fuente y por semana ISO (2026 completo) + por día (desde 2026-05-01):
- `spend`, `impr`, `clicks`, `cpm`, `cpc`, `cpl`, `registros`, `asignados`, `cvr`
- metas: `meta_orig`, `meta_recal` (=meta_orig×RECAL[fuente]), `actual`, `prev` (YoY)
- bloque `proyeccion` (ver Step 2)
- bloque `hitos` (copiado de hitos.json)
- `updated` (fecha pasada por arg, no usar Date.now)

Estructura de salida (esqueleto):
```python
out = {
  "updated": sys.argv[1],          # fecha en YYYY-MM-DD, pasada explícita
  "fuentes": ["WEB","lead_forms","Estudio Inmueble"],
  "semanal": { fuente: [ {"w":"2026-W23","spend":..,"impr":..,"clicks":..,
                          "cpm":..,"cpc":..,"cpl":..,"registros":..,"asignados":..,"cvr":..,
                          "meta_orig":..,"meta_recal":..,"actual":..,"prev":..} ] },
  "diario":  { fuente: [ {"d":"2026-05-01", ...mismas métricas diarias...} ] },
  "hitos":   [...],
  "proyeccion": {...},             # Step 2
}
```

- [ ] **Step 2: Modelo de proyección Q2+Q3 (optimista / conservador)**

Transparente y por fuente. Base = run-rate de las **últimas 4 semanas completas** por fuente: `asignados_base`, `cvr_base`, `cpl_base`. Proyectar semana a semana hasta fin de Q3 (sep) aplicando factores multiplicativos nombrados:

```python
# Factores por escenario (calibrados con FINDINGS de Task 4; defaults abajo).
# demanda: efecto mundial+festivos sobre registros. cpl: inflación de subasta. cvr: nivel de conversión.
SCEN = {
  "conservador": {
    # por bloque de calendario -> (demanda, cpl_mult, cvr_mult)
    "mundial":   (0.88, 1.20, 1.00),   # 11-jun a 19-jul
    "post":      (0.97, 1.08, 1.00),   # 20-jul -> fin Q3, normaliza lento
  },
  "optimista": {
    "mundial":   (0.93, 1.10, 1.02),
    "post":      (1.05, 0.98, 1.05),   # rebote + CPM normaliza + CVR recupera
  },
}
# asignados_proj(semana) = registros_base*demanda * (cvr_base*cvr_mult)
# CPL implícito = cpl_base*cpl_mult (para narrar costo, no entra en asignados directo)
```
Salida `proyeccion`: por fuente y por escenario, lista semanal `{w, asignados, cpl}`, más el **acumulado Q2 cierre** y **Q3** vs meta original y recalibrada, y la **banda** (cono) optimista–conservador para el TOTAL.

- [ ] **Step 3: Ejecutar y validar**

```bash
cd /home/administrador/habi/tableros-marketing/diagnostico-performance-co
python3 build_data.py 2026-06-15
python3 -c "
import json; d=json.load(open('data.json'))
print('fuentes:', d['fuentes'])
print('semanas WEB:', len(d['semanal']['WEB']))
print('dias WEB:', len(d['diario']['WEB']), '(debe arrancar 2026-05-01)')
print('proy keys:', list(d['proyeccion'].keys()))
"
```
Expected: 3 fuentes, ~23 semanas, ~46 días desde 1-may, bloque proyeccion presente.

- [ ] **Step 4: Validar suma de asignados proyectados es coherente**

```bash
python3 -c "
import json; d=json.load(open('data.json'))
# La proyección conservadora debe ser <= optimista en el acumulado total.
print(d['proyeccion'])" | head -40
```
Expected: conservador ≤ optimista en todos los acumulados.

- [ ] **Step 5: Commit**

```bash
cd /home/administrador/habi/tableros-marketing
git add diagnostico-performance-co/build_data.py diagnostico-performance-co/data.json
git commit -m "diagnostico-performance-co: build_data + escenarios de proyección Q2+Q3"
```

---

## Task 6: index.html — informe narrativo (5 capítulos + resumen)

**Files:**
- Create: `diagnostico-performance-co/index.html`

- [ ] **Step 1: Maquetar el HTML** reusando el look & feel de `analisis-asignados-co/index.html` (mismo header con "← Hub", nav de capítulos, tipografía, tarjetas). Cargar `data.json` con `fetch('./data.json')`. Chart.js vía CDN. Estructura:
  - Header + nav: Resumen · Cap.1 Varas · Cap.2 Inversión&Costos · Cap.3 CPL&Captación · Cap.4 Conversión · Cap.5 Proyección.
  - **Resumen ejecutivo**: tarjetas con gap Q2 vs 3 varas + descomposición de palancas + 1 frase por escenario.
  - **Cap.1**: chart de barras/líneas cumplimiento semanal por fuente vs meta_orig / meta_recal / prev.
  - **Cap.2**: líneas semanales de spend, CPM, CPC por fuente + zoom diario desde 1-may con bandas de hito (plugin de anotación o regiones sombreadas) descritas en prosa.
  - **Cap.3**: CPL por fuente + registros por fuente (semanal y diario).
  - **Cap.4**: CVR registro→asignado por fuente (semanal), con línea vertical en 12-mar (Backbone) y la cifra del −16% confirmada.
  - **Cap.5**: cono optimista–conservador del TOTAL + tabla por fuente con acumulado Q2/Q3 vs metas. Supuestos visibles.
  - Tono ejecutivo (memoria `feedback_informe_tono`): sin jerga, framing positivo + ROI.

- [ ] **Step 2: Servir localmente y verificar**

```bash
cd /home/administrador/habi/tableros-marketing/diagnostico-performance-co
python3 -m http.server 8099 &
sleep 1; curl -s http://localhost:8099/ | grep -c "canvas"; kill %1
```
Expected: cuenta de `<canvas>` > 0 y la página carga sin error. Abrir en navegador para verificar charts (usar skill `verify` o screenshot).

- [ ] **Step 3: Commit**

```bash
cd /home/administrador/habi/tableros-marketing
git add diagnostico-performance-co/index.html
git commit -m "diagnostico-performance-co: informe HTML (5 capítulos + resumen)"
```

---

## Task 7: Registrar en el hub + deploy

**Files:**
- Create: `diagnostico-performance-co/meta.json`

- [ ] **Step 1: Crear meta.json** (orden al final de la sección, ver memoria `feedback_hub_orden`)

```json
{
  "title": "Diagnóstico Performance CO — Mundial 2026",
  "description": "Por qué no cumplimos metas (3 palancas: inversión, CPL, conversión) por fuente, y proyección Q2+Q3 optimista/conservador.",
  "country": "CO",
  "section": "analisis",
  "order": 99
}
```
Ajustar `section`/`order` según convención del hub (revisar `hub.config.json` para el orden correcto vs los otros análisis).

- [ ] **Step 2: Regenerar el hub si aplica**

Revisar `tableros-marketing/scripts/` por el generador del `index.html` raíz (es generado, no editar a mano — memoria `feedback_hub_orden`). Correrlo.

- [ ] **Step 3: Verificar que el hub lista el nuevo informe**

```bash
cd /home/administrador/habi/tableros-marketing
grep -c "diagnostico-performance-co" index.html
```
Expected: > 0.

- [ ] **Step 4: Commit + push (pedir confirmación al usuario antes de push, dispara deploy GH Actions)**

```bash
git add diagnostico-performance-co/meta.json index.html
git commit -m "diagnostico-performance-co: registro en hub"
# git push  <- confirmar con el usuario; dispara deploy a GitHub Pages
```

---

## Self-Review (cobertura del spec)

- ✅ Informe HTML narrativo, CO, fuentes WEB/Lead Forms/Habímetro → Tasks 6, 1, 2.
- ✅ Marco causal 3 palancas (Inversión × 1/CPL × CVR) → estructura de capítulos Task 6 + métricas Tasks 1,2,5.
- ✅ Granularidad semanal + zoom diario desde 1-may con hitos descritos → Tasks 2,4,5,6.
- ✅ Atribución por UTM (`registro_unico_utm_mkt_colombia`) → Task 1 (validada 100% match).
- ✅ Triple vara (meta original / recalibrada −16% / YoY) → Task 3 + Cap.1.
- ✅ CPL/CPM/CPC por fuente → Tasks 1,4,5.
- ✅ Conversión registro→asignado confirmando −16% → Task 2 (validación) + Cap.4.
- ✅ Proyección Q2+Q3 optimista/conservador con supuestos explícitos → Task 5 + Cap.5.
- ✅ Reconciliación de ejes (UTM vs fuente) → resuelta: etiquetas idénticas (WEB/lead_forms/Estudio Inmueble), verificado 2026-06-15.
- ✅ Registro en hub + deploy → Task 7.

**Riesgo abierto:** las metas por fuente pueden no estar en `okr-marketing/data.json` a nivel semanal (Task 3 Step 1 lo verifica; fallback = re-parsear el CSV del sheet con `parse_sheet()`).
