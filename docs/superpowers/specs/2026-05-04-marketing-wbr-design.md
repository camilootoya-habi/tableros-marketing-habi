# Marketing WBR — Diseño (Bloque 1: Matriz Dupont)

**Fecha:** 2026-05-04
**Autor:** Camilo Otoya (con asistencia de Jean-Claude)
**Estado:** Spec aprobado, listo para implementación
**Scope de este spec:** Bloque 1 (matriz Dupont comparativa) del tablero "Marketing WBR".
El Bloque 2 (segundo análisis) se diseñará en un spec aparte.

---

## 1. Contexto

El Hub `tableros-marketing-habi` agrupa los dashboards de Growth & Marketing de Habi.
Hoy ya hay tableros de funnel sellers, OKR marketing, leads incompletos y otros.

Falta una vista **Weekly Business Review** que permita ver de un vistazo cómo va
la performance reciente vs. el período inmediatamente anterior, partido por canal
de marketing y siguiendo la lógica Dupont (output = inversión × eficiencias).

El tablero se compone de **dos bloques**. Este spec cubre solo el primero:

- **Bloque 1 (este spec):** matriz comparativa Dupont — canales en eje Y, indicadores en eje X.
- **Bloque 2 (futuro):** TBD — se diseñará después.

---

## 2. Objetivos

- Detectar de un vistazo qué canal mejoró/empeoró significativamente vs. la semana
  (o período) anterior.
- Aplicar lógica Dupont: el output (Calificados) se descompone en sus drivers
  (Inversión, CPL, Registros, CVR Reg→Cal).
- Apto para reunión de WBR ejecutivo: información densa, comparable, accionable.

**No-objetivos (out of scope explícito):**

- Asignados como indicador. Acordamos dejarlo fuera de la ecuación por ahora;
  el lag entre calificación y asignación distorsiona el cohort. Si entra después,
  vuelve también la "meta" (ver §10).
- Meta de cumplimiento. No se incluye en esta primera matriz.
- Drill-down por campaña dentro de un canal.

---

## 3. Decisiones clave (tomadas en brainstorming)

| Decisión | Valor | Razón |
|---|---|---|
| País de la primera entrega | **CO** (selector preparado para MX) | Replicar a MX en una segunda entrega, igual que Funnel Sellers |
| Ventanas de tiempo | 7 / 14 / 28 / 56 días, default 7 | Cubre el rango natural de WBR ejecutivo |
| Período comparativo | Los N días inmediatamente anteriores a la ventana actual | Decisión del usuario |
| Tipo de cohort | **Cohort por `fecha_creacion`** del lead | 91% de leads se califican en 24h, 97.7% en 7d → cohort funciona sin sesgo material |
| Métrica top (output) | **Calificados** | Sin asignados, calificados es el último eslabón medible por cohort |
| Definición de Calificado | `estado_id IN (20, 63)` (no_gestionado + sin_pricing_inicial) en `historico_estado_v2` | Definición canónica usada en Funnel Sellers |
| Indicadores en orden | Inversión → CPL → Registros → CVR R→C → Calificados | Orden Dupont (input → eficiencia → output) |
| Coloreo significativo | **±10% relativo** | Igual para conteos, montos y tasas (una tasa de 20%→15% se lee como -25%, no -5pp) |
| Inversión: coloreo | **Sin coloreo** (subir/bajar inversión no es per se bueno/malo) | Solo se muestra el delta, sin verde/rojo |
| Canales (eje Y) | `mkt_channel_medium` con CASE de fallback (ver §5) | Patrón usado por el equipo de marketing |
| Filtro de fuentes | `fuente_id IN (3, 7, 20, 35, 39, 47)` (las 6 fuentes de marketing) | Mismo filtro de Funnel Sellers |
| Conteo de registros | `COUNT(*)` (sin filtrar por nid) — usar `negocio_id` cuando nid es NULL | 13% de leads no tienen nid, mayoría en Estudio Inmueble (37% de su volumen) |
| Atribución de inversión | JOIN `i.campana = m.mkt_campaign_name` del UTM dict | Mismo método del usuario |

---

## 4. Estructura del tablero

### 4.1 Ubicación y URL

- **Path local:** `~/habi/tableros-marketing/marketing-wbr/`
- **URL prod:** `https://camilootoya-habi.github.io/tableros-marketing-habi/marketing-wbr/`
- **Card en HUB** (`index.html` root, columna *Dashboards*):
  ```html
  <a class="card" href="https://camilootoya-habi.github.io/tableros-marketing-habi/marketing-wbr/">
    <h2><span class="country">CO &amp; MX</span>Marketing WBR</h2>
    <p>Weekly Business Review: matriz Dupont por canal con comparativos vs período anterior.</p>
  </a>
  ```

### 4.2 Layout de la página

1. **Header:** título "Marketing WBR", back link al hub, theme toggle.
2. **Selectores:**
   - País: radio buttons CO / MX (CO activo, MX placeholder con mensaje "Próximamente").
   - Ventana: botones 7 / 14 / 28 / 56 días (default 7).
   - Etiqueta del período: `Período actual: dd/mm - dd/mm · vs. dd/mm - dd/mm`.
3. **Bloque 1: Matriz Dupont** (esta entrega).
4. **Bloque 2:** placeholder vacío (se llenará en spec futuro).

### 4.3 Persistencia

- País y ventana se persisten en `localStorage` (claves `wbr-country`, `wbr-window`).
- Theme (dark/light) usa la misma clave que los demás tableros (`tablero-theme`).

---

## 5. Lógica de canales (eje Y)

Para cada lead se calcula su `channel` con esta lógica (validada con la query del usuario):

```sql
channel = CASE
  WHEN g.campana_mercadeo IS NULL OR g.campana_mercadeo = ''
    THEN CONCAT(g.fuente, ' Direct')                      -- ej. "Broker Direct", "Estudio Inmueble Direct"
  WHEN m.mkt_channel_medium IS NULL OR m.mkt_channel_medium = ''
    THEN g.campana_mercadeo                               -- fallback long-tail (campaña sin clasificar)
  ELSE m.mkt_channel_medium                               -- clasificado por UTM dict
END
```

Donde `m` es el resultado del LEFT JOIN al UTM dict deduplicado:

```sql
WITH utm_dedup AS (
  SELECT *
  FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
  QUALIFY ROW_NUMBER() OVER(PARTITION BY campana_mercadeo_original ORDER BY campana_mercadeo_original) = 1
)
... LEFT JOIN utm_dedup m ON g.campana_mercadeo = m.campana_mercadeo_original
```

### Canales esperados (CO últimos 90d, post-filtro 6 fuentes)

| Canal | Registros 90d | Tipo |
|---|---|---|
| WEB Paid | ~18,700 | Paid (UTM) |
| Estudio Inmueble Paid | ~14,600 | Paid (UTM) |
| Estudio Inmueble Direct | ~9,300 | Orgánico (sin UTM) |
| WEB Direct | ~8,100 | Orgánico (sin UTM) |
| lead_forms Paid | ~3,300 | Paid (UTM) |
| WEB SAC | ~1,500 | Orgánico (UTM) |
| CRM Direct | ~1,100 | Orgánico (sin UTM) |
| comercial Direct | ~1,080 | Orgánico (sin UTM) |
| Broker Direct | ~750 | Orgánico (sin UTM) |
| WEB Community | ~370 | Orgánico (UTM) |
| WEB Referral | ~170 | Orgánico (UTM) |
| Long tail (campañas sin clasificar) | <200 | Fallback |

**Decisión sobre el long tail:** dejar las filas tal cual genera el CASE. Si en
operación suman <0.5% del total, agruparlos como "Otros sin clasificar" en el
front. La decisión final se toma cuando veamos data real en producción.

---

## 6. Lógica de indicadores

Para cada `(canal, ventana)`:

| Indicador | Definición |
|---|---|
| **Inversión** | `SUM(spend)` de la inversión cuyo `mkt_campaign_name` mapea a este canal vía UTM dict, en el rango de fechas |
| **Registros** | `COUNT(*)` sobre `tabla_inmuebles_general` con `fecha_creacion` ∈ ventana |
| **Calificados** (cohort) | `COUNT(*)` de leads del cohort cuyo `negocio_id` aparece en `historico_estado_v2` con `estado_id IN (20, 63)` (cualquier fecha) |
| **CVR Reg→Cal** | `Calificados / Registros` |
| **CPL** | `Inversión / Registros` (null si Inversión es null) |

### Identificación del lead

- Cada fila de `tabla_inmuebles_general` es **un registro**.
- El join al histórico se hace por `negocio_id` (que está presente incluso cuando `nid` es NULL).
- No se filtra por `nid IS NOT NULL`; eso descartaría 13% del volumen total y 37% de Estudio Inmueble.

### Fila TOTAL

- Suma simple en Inversión, Registros, Calificados (de los canales mostrados).
- CPL = `Σ Inversión / Σ Registros` (no promedio de CPLs por canal).
- CVR = `Σ Calificados / Σ Registros` (no promedio de CVRs por canal).

---

## 7. Ventanas y comparativos

- **Hoy** = `CURRENT_DATE()` (en la zona horaria del workflow, UTC).
- **Ventana actual** = `[hoy - N, hoy - 1]` (N días, sin contar hoy).
- **Ventana anterior** = `[hoy - 2N, hoy - N - 1]` (los N días inmediatamente anteriores).
- N ∈ {7, 14, 28, 56}.

Ejemplo con N=7 y hoy=2026-05-04:
- Actual: 2026-04-27 → 2026-05-03
- Anterior: 2026-04-20 → 2026-04-26

---

## 8. Coloreo

Para cada celda con valor numérico se calcula:

```
delta = (actual - prev) / prev      // relativo, ±10% para activar color
```

Reglas de color:

| Indicador | Verde si | Rojo si | Sin color |
|---|---|---|---|
| Calificados | `delta > +0.10` | `delta < -0.10` | resto |
| Registros | `delta > +0.10` | `delta < -0.10` | resto |
| CVR Reg→Cal | `delta > +0.10` | `delta < -0.10` | resto |
| CPL | `delta < -0.10` (mejor = más barato) | `delta > +0.10` | resto |
| **Inversión** | — (nunca) | — (nunca) | siempre sin color, solo muestra delta |

Casos especiales:

- `prev = 0` y `actual > 0` → verde (mismo tinte que el coloreo normal); el delta se muestra como "+∞" o "nuevo".
- `prev = 0` y `actual = 0` → neutro.
- `actual = null` (canal sin inversión) → "—" sin coloreo.
- Tasas: el delta se calcula sobre la tasa (ej. 20% → 15% es `(15-20)/20 = -25%`).

**Background sutil sobre dark theme:**
- Verde: `rgba(22, 163, 74, 0.13)` (tinte de `#16a34a`)
- Rojo: `rgba(220, 38, 38, 0.13)` (tinte de `#dc2626`)

---

## 9. UI

### Layout de la matriz

```
┌──────────────────────┬──────────┬───────┬───────────┬──────────┬────────────┐
│ Canal                │ Inversión│  CPL  │ Registros │ CVR R→C  │ Calificados│
├──────────────────────┼──────────┼───────┼───────────┼──────────┼────────────┤
│ TOTAL                │  $XXM    │ $X.Xk │   X,XXX   │  XX.X%   │   X,XXX    │
│ (sticky, bold)       │  Δ +5%   │ Δ -3% │   Δ +12% 🟢│  Δ -25% 🔴│  Δ -8%     │
├──────────────────────┼──────────┼───────┼───────────┼──────────┼────────────┤
│ WEB Paid             │  ...     │  ...  │    ...    │   ...    │    ...     │
│ Estudio Inmueble Paid│  ...     │  ...  │    ...    │   ...    │    ...     │
│ ...                  │          │       │           │          │            │
│ WEB Direct           │   —      │   —   │    ...    │   ...    │    ...     │
│ ...                  │          │       │           │          │            │
└──────────────────────┴──────────┴───────┴───────────┴──────────┴────────────┘
```

### Detalles visuales

- **Por celda:**
  - Línea 1: valor actual.
  - Línea 2: delta `Δ ±X%` (más pequeño, color del coloreo).
  - Background: tinte verde/rojo según las reglas de §8.
  - Hover: tooltip con `actual: X · anterior: Y · Δ: ±Z%`.
- **Formato de números:**
  - Inversión: `$1.2M`, `$345k`, `$12,345` (umbrales: 1M, 1k).
  - CPL: `$12.3k`, `$1,234` (umbral 1k).
  - Registros, Calificados: separador de miles `1,234`.
  - CVR: `12.3%` (1 decimal).
- **Fila TOTAL:** sticky en top, fondo ligeramente distinto (`var(--card)` más opaco), bold.
- **Ordenamiento:** click en header → ASC/DESC por esa columna; default DESC por Registros (Total siempre arriba).
- **Canal sin valor:** "—" (em-dash) sin coloreo.

### Tema

Mismas variables CSS que los demás tableros (ver `general.md` de la memoria):

- Dark: `--bg #0f172a`, `--card #1e293b`, `--accent #818cf8`, etc.
- Light: las mismas overrides que el resto.
- Toggle con la misma clave `localStorage` (`tablero-theme`).

### Favicon

Megáfono SVG estándar, igual que el resto:

```html
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📢</text></svg>">
```

---

## 10. Pipeline de datos

### 10.1 Archivos

```
~/habi/tableros-marketing/marketing-wbr/
├── index.html       ← UI con matriz, selectores, theme toggle
├── query.sql        ← query parametrizada (CO en esta entrega; MX se agrega después)
├── build_data.py    ← (opcional) transformación BQ JSON → shape compacto
└── data.json        ← auto-update diario
```

### 10.2 Queries (dos separadas, se combinan en Python)

**Decisión:** dos queries independientes — una para leads+calificados, otra para spend.
Se combinan en `build_data.py`. Esto evita los problemas de duplicación que
introduce un join de spend a la granularidad de lead, y permite escanear cada
fuente solo una vez.

**Query A — leads + calificados:**

```sql
-- query_leads.sql (CO; misma estructura para MX)
WITH utm_dedup AS (
  SELECT *
  FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
  QUALIFY ROW_NUMBER() OVER(PARTITION BY campana_mercadeo_original ORDER BY campana_mercadeo_original) = 1
),
leads AS (
  SELECT
    g.negocio_id,
    DATE(g.fecha_creacion) AS dia,
    CASE
      WHEN g.campana_mercadeo IS NULL OR g.campana_mercadeo = ''
        THEN CONCAT(g.fuente, ' Direct')
      WHEN m.mkt_channel_medium IS NULL OR m.mkt_channel_medium = ''
        THEN g.campana_mercadeo
      ELSE m.mkt_channel_medium
    END AS channel
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` g
  LEFT JOIN utm_dedup m ON g.campana_mercadeo = m.campana_mercadeo_original
  WHERE g.fuente_id IN (3, 7, 20, 35, 39, 47)
    AND DATE(g.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
    AND DATE(g.fecha_creacion) < CURRENT_DATE()
),
cal AS (
  SELECT negocio_id, MIN(fecha_actualizacion) AS cal_ts
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_historico_estado_v2`
  WHERE estado_id IN (20, 63)
  GROUP BY 1
)
SELECT
  l.dia,
  l.channel,
  COUNT(*) AS reg,
  COUNTIF(c.cal_ts IS NOT NULL) AS cal
FROM leads l
LEFT JOIN cal c ON c.negocio_id = l.negocio_id
GROUP BY 1, 2
ORDER BY 1, 2
```

**Query B — spend:**

```sql
-- query_spend.sql (CO)
WITH utm_dedup AS (
  SELECT *
  FROM `sellers-main-prod.bi_co.registro_unico_utm_mkt_colombia`
  QUALIFY ROW_NUMBER() OVER(PARTITION BY mkt_campaign_name ORDER BY mkt_campaign_name) = 1
)
SELECT
  i.date AS dia,
  m.mkt_channel_medium AS channel,
  ROUND(SUM(i.spend), 0) AS spend
FROM `papyrus-data.habi_wh_bi.resumen_inversiones_mkt_co` i
LEFT JOIN utm_dedup m ON i.campana = m.mkt_campaign_name
WHERE i.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
  AND i.date < CURRENT_DATE()
  AND m.mkt_channel_medium IS NOT NULL  -- spend sin canal queda fuera (reportar match rate)
GROUP BY 1, 2
ORDER BY 1, 2
```

**Combinación en `build_data.py`:**

```python
# Pseudocódigo
leads = json.load(open('/tmp/wbr_leads_co.json'))   # [{dia, channel, reg, cal}, ...]
spend = json.load(open('/tmp/wbr_spend_co.json'))   # [{dia, channel, spend}, ...]

by_day = defaultdict(dict)
for r in leads:
    by_day[r['dia']][r['channel']] = {'reg': r['reg'], 'cal': r['cal'], 'spend': None}
for s in spend:
    cell = by_day[s['dia']].setdefault(s['channel'], {'reg': 0, 'cal': 0, 'spend': None})
    cell['spend'] = s['spend']

json.dump({'updated': today, 'co': {'by_day': by_day}, 'mx': {'by_day': {}}}, out)
```

### 10.3 JSON shape

```json
{
  "updated": "2026-05-04",
  "co": {
    "by_day": {
      "2026-04-01": {
        "WEB Paid":               {"reg": 234, "cal": 78, "spend": 1234567},
        "Estudio Inmueble Paid":  {"reg": 120, "cal": 45, "spend": 234567},
        "WEB Direct":             {"reg": 89,  "cal": 23, "spend": null},
        "...": {}
      },
      "2026-04-02": { "...": {} }
    }
  },
  "mx": { "by_day": {} }
}
```

- Granularidad **diaria** por (canal, día); el front agrega para 7/14/28/56d en cliente.
- 180 días de historia (suficiente para ventana 56d × 2 + holgura).
- Tamaño estimado: ~150 días × ~15 canales × 2 países = ~4,500 entries → ~200KB.

### 10.4 Auto-update

Step nuevo dentro del workflow consolidado `.github/workflows/update-data.yml`:

1. `bq query --format=json --max_rows=10000 < marketing-wbr/query_leads.sql > /tmp/wbr_leads_co.json`
2. `bq query --format=json --max_rows=10000 < marketing-wbr/query_spend.sql > /tmp/wbr_spend_co.json`
3. `python marketing-wbr/build_data.py /tmp/wbr_leads_co.json /tmp/wbr_spend_co.json marketing-wbr/data.json`
4. Commit incluye `marketing-wbr/data.json` en el step final del workflow.

Mismo cron 13:00 UTC (= 7am MX / 8am CO). Sin nuevo workflow.

---

## 11. Riesgos y supuestos

- **Long tail UTM no clasificado:** ~150 leads en 90d caen en el fallback
  `g.campana_mercadeo` y aparecen como "canales" con nombre raro. Decisión final
  (mostrar tal cual vs. agrupar como "Otros sin clasificar") cuando veamos data
  en producción.
- **Cohort de calificados:** subreporta ~3-5% en ventanas cortas (la cola de
  calificación post-7d). Está dentro del umbral del 10% que activa color, así que
  no genera falsos positivos.
- **Atribución de inversión:** requiere que `i.campana` de la tabla de spend matchee
  con `m.mkt_campaign_name` del UTM dict. Las campañas que no matchean dejan su
  spend sin atribuir (no aparece en ningún canal). Reportar el match rate al
  validar la query con datos reales.
- **MX queda preparado pero no entregado** en esta primera versión. La query y la
  shape del JSON soportan ambos países; falta solo escribir la versión MX (tablas
  equivalentes confirmadas en otros tableros) y enchufarla.
- **Zona horaria:** las queries usan `CURRENT_DATE()` que se evalúa en la zona
  horaria del workflow (UTC). `fecha_creacion` está en hora local del lead (CO).
  Para ventanas de 7+ días el offset (max ~5h) es despreciable. Si el segundo
  bloque del WBR mide ventanas más finas (intra-día), revisar.

---

## 12. Definition of done (Bloque 1)

- [ ] Carpeta `marketing-wbr/` creada con `index.html`, `query.sql`, `build_data.py`.
- [ ] Card agregada al HUB (`index.html` root).
- [ ] Query corre en BQ devolviendo data válida para CO últimos 180 días.
- [ ] `data.json` generado y commiteado.
- [ ] Step nuevo en `update-data.yml` integrado al workflow consolidado.
- [ ] Tablero deployado a GitHub Pages y accesible en la URL.
- [ ] Selectores de país (CO activo) y ventana (7/14/28/56) funcionan.
- [ ] Matriz muestra TOTAL + canales con coloreo correcto (±10% relativo).
- [ ] Tooltip por celda con actual/anterior/delta.
- [ ] Theme toggle persistido funciona.

---

## 13. Roadmap post-entrega

1. **MX:** replicar query con tablas equivalentes (`papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general`,
   `sellers-main-prod.mx_rds_staging.habi_db_history_state` con `state_id IN (20,63)`,
   y la tabla equivalente de UTM dict para MX).
2. **Bloque 2:** definir y construir el segundo análisis del WBR (spec aparte).
3. **Asignados + meta:** revisar el lag real y, si es viable, agregar Asignados a
   la matriz con su columna de meta (cumplimiento solo en esa columna).
4. **Drill-down por campaña:** click en canal → vista detallada por campaña.
