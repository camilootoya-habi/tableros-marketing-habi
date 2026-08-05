# Tablero asignación MM vs INMO (CO) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el tablero `asignacion-co/` del hub de marketing con tres lentes apiladas (cosechas por fecha de creación, llegadas a INMO, llegadas a MM) más un bloque de reconciliación con el WBR mart.

**Architecture:** Un `query.sql` que arma un CTE `base` a nivel `nid` y emite filas de **grano diario** en formato largo; el frontend bucketea a semana/mes/ciclo comercial y muestra los últimos 20 períodos. Las métricas de tiempo (mediana, p90) **no** son re-agregables desde grano diario, así que vienen pre-calculadas desde SQL para las 3 granularidades. El tablero entra por **auto-discovery** del cron (`meta.json` con `query`), sin pipeline a-medida en `update-data.yml`.

**Tech Stack:** BigQuery (SQL estándar), HTML/CSS/JS vanilla, Chart.js vía el helper `mkChart` del template del repo, Python 3 solo para verificaciones locales.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-04-tablero-asignacion-co-design.md`. Ante cualquier duda de definición, el spec manda.
- País: **solo Colombia**. México es fase 2.
- **Nunca editar el `index.html` de la raíz** — es generado por `scripts/build_hub.py`.
- Gráficas **siempre con Chart.js** vía `mkChart`, nunca SVG a mano.
- Facturar BQ en `sellers-main-prod`. `papyrus-data` y `papyrus-master` **no** permiten crear jobs con estas credenciales: se leen cross-project con path completo.
- pipeline_id: MM = `798578615` · INMO = `803674753`.
- ⚠️ **`1679217` ("Sellers CO") NO es un producto: es el pipeline donde nace todo deal** (1.373.130 nids en 940 días, más que el universo entero de leads de la ventana). Tampoco lo son los pipelines de MX (`15290604`, `638550350`, `10867264`). **`prod_1` se calcula SOLO entre MM e INMO**; todo lo demás se ignora. Las métricas de producto se condicionan además a que el lead esté asignado (`d_primera_asig IS NOT NULL`). Los asignados que nunca entraron a MM ni INMO se cuentan en una métrica propia, `sin_producto`.
- ⚠️ **Cobertura de los pipelines nuevos: MM arranca 2025-09-18 e INMO 2025-10-02.** Los períodos anteriores tienen las columnas de producto en cero **por construcción, no por caída**. El frontend los marca "sin cobertura" (ver Task 5). Las métricas de asignación (`asig_30d`, `asig_ever`, `gabi_30d`, `directo_30d`) sí tienen data desde 2024-01 y se muestran normal.
- `hubspot.historical`: particionada por MONTH en `fecha`, clusterizada por `propiedad`, `valor` es STRING, **~5 h de rezago**. Filtrar SIEMPRE por `propiedad` y por `fecha`.
- **`bi_co.seguimiento_asignacion_ibuyer_co.pipeline` es snapshot** — prohibido usarlo para la secuencia de productos. De esa tabla solo se usan `fecha_asignacion`, `tipo_asignacion`, `tipo`, `equipo_inicial`, `area_metropolitana`, `fuente`.
- **`product_qualified` no tiene fecha ni historial** — se usa solo como atributo de estado final, jamás como fecha ni como secuencia.
- ⚠️ **La secuencia de productos se compara SIEMPRE con TIMESTAMP, nunca con DATE.** 1.729 nids tienen eventos de MM e INMO el mismo día y a nivel DATE su orden es indefinido (el resultado cambiaría entre corridas del cron). Las fechas se derivan de los timestamps solo para agrupar por período y para medir diferencias en días.
- Percentiles: **mediana y p90, nunca promedio**.
- `bq query --format=json` devuelve **todos los valores como STRING** — el frontend debe hacer `Number()` en cada métrica.
- Nunca usar `ANY_VALUE` para tomar "el primero" de un grupo: usar `ARRAY_AGG(... ORDER BY ... LIMIT 1)[OFFSET(0)]`.
- Ventana del SQL: `dias_ventana = 760` días (cubre 20 períodos mensuales + colchón de maduración de 90 d).
- Commits en español, imperativo, con el prefijo del tablero: `feat(asignacion-co): ...`.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `asignacion-co/meta.json` | Metadata de la card + declaración de `query`, `max_rows`, `maximum_bytes_billed`. |
| `asignacion-co/query.sql` | CTE `base` a nivel nid + emisión de las filas de las 3 lentes, la reconciliación y los tiempos. Único punto de verdad de las definiciones. |
| `asignacion-co/index.html` | Selector de granularidad + filtros, las 3 lentes apiladas y el bloque de Conclusiones. Lee `data.json` con `fetch`. |
| `asignacion-co/data.json` | Generado por el cron. No se edita a mano (se genera local para desarrollo). |
| `docs/superpowers/plans/2026-08-04-tablero-asignacion-co.md` | Este plan. |

**Contrato del `data.json`** (array de objetos, salida cruda de `bq --format=json`). Dos familias de filas discriminadas por `kind`:

- `kind='count'` — grano diario: `{kind, lente, d, dim, dim_val, metrica, n}`
  - `lente` ∈ `A` | `B` | `C` | `REC`
  - `d` = fecha del ancla (lente A: creación; B: llegada a INMO; C: llegada a MM; REC: creación)
  - `dim` ∈ `total` | `fuente` | `area` | `equipo`; `dim_val` = el valor (o `'total'`)
  - `metrica` = nombre de la métrica (ver cada tarea); `n` = conteo de nids
- `kind='tiempo'` — pre-agregado: `{kind, gran, periodo, salto, mediana, p90, n}`
  - `gran` ∈ `semana` | `mes` | `ciclo`; `salto` ∈ `creacion_gabi` | `gabi_mm` | `mm_inmo` | `inmo_mm`

---

## Task 1: Scaffolding del tablero y verificación del pipeline de datos

Deja el tablero registrado y corriendo end-to-end con una métrica trivial, para separar los problemas de plomería de los de lógica.

**Files:**
- Create: `asignacion-co/meta.json`
- Create: `asignacion-co/query.sql`
- Create: `asignacion-co/index.html`

**Interfaces:**
- Consumes: nada.
- Produces: la carpeta `asignacion-co/` reconocida por `scripts/run_queries.py` (job con `sql_path` y `data_path`), y un `data.json` local válido.

- [ ] **Step 1: Crear `asignacion-co/meta.json`**

```json
{
  "title": "Asignación · MM vs INMO (CO)",
  "description": "Tres lentes: cosechas por fecha de creación, llegadas a INMO y llegadas a MM con sus rutas de origen (directo, GABI, cruce entre productos). Incluye reconciliación con el WBR mart.",
  "country": "CO",
  "section": "dashboard",
  "order": 200,
  "query": "query.sql",
  "maximum_bytes_billed": 5000000000,
  "max_rows": 300000
}
```

- [ ] **Step 2: Crear `asignacion-co/query.sql` con el universo mínimo**

```sql
-- Tablero asignación MM vs INMO (CO)
-- Grano de salida: filas largas {kind, lente, d, dim, dim_val, metrica, n}
--   + filas {kind='tiempo', gran, periodo, salto, mediana, p90, n}
-- El frontend bucketea las filas kind='count' a semana/mes/ciclo y toma los últimos 20 períodos.
-- Ventana: 760 días (20 períodos mensuales + colchón de maduración de 90 d).
-- Definiciones: docs/superpowers/specs/2026-08-04-tablero-asignacion-co-design.md

WITH leads AS (
  SELECT
    CAST(t.nid AS STRING)                        AS nid,
    DATE(t.fecha_creacion)                       AS d_creacion,
    t.fuente_id                                  AS fuente_id,
    COALESCE(NULLIF(TRIM(t.fuente), ''), '(sin fuente)')                AS fuente,
    COALESCE(NULLIF(TRIM(t.area_metropolitana), ''), '(sin área)')      AS area
  FROM `papyrus-data.habi_wh_bi.tabla_inmuebles_general` t
  WHERE t.nid IS NOT NULL
    AND DATE(t.fecha_creacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 760 DAY)
    AND DATE(t.fecha_creacion) <  CURRENT_DATE()
)
SELECT 'count' AS kind, 'A' AS lente, d_creacion AS d,
       'total' AS dim, 'total' AS dim_val, 'creados' AS metrica,
       COUNT(DISTINCT nid) AS n
FROM leads
GROUP BY d
```

- [ ] **Step 3: Dry-run para medir bytes y validar sintaxis**

Run:
```bash
cd ~/habi/tableros-marketing
bq query --nouse_legacy_sql --dry_run --format=none \
  --project_id=sellers-main-prod < asignacion-co/query.sql
```
Expected: `Query successfully validated` y un upper bound por debajo de 5 GB (referencia: el CTE de `historical` acotado mide 2,03 GB; este paso, solo con `leads`, debe estar bien por debajo).

- [ ] **Step 4: Correr el job por auto-discovery y verificar el `data.json`**

Run:
```bash
cd ~/habi/tableros-marketing
python3 scripts/run_queries.py --only asignacion-co
python3 -c "
import json; r=json.load(open('asignacion-co/data.json'))
print('filas', len(r)); print('ejemplo', r[0])
assert len(r) > 600, 'esperaba ~760 días de cosechas'
assert set(r[0]) == {'kind','lente','d','dim','dim_val','metrica','n'}, r[0].keys()
print('OK')"
```
Expected: `✓ asignacion-co`, ~700-760 filas, y `OK`. Si falla con Access Denied, revisar que la query use el path completo de `papyrus-data` y que se facture en `sellers-main-prod`.

- [ ] **Step 5: Crear `asignacion-co/index.html` desde el template**

```bash
cd ~/habi/tableros-marketing
cp scripts/templates/dashboard.html asignacion-co/index.html
```

Luego, en `asignacion-co/index.html`, ajustar el `<title>` y el `<h1>` a `Asignación · MM vs INMO (CO)` y dejar el resto del template intacto por ahora.

- [ ] **Step 6: Verificar que el hub lo recoge y que los tests del generador siguen verdes**

Run:
```bash
cd ~/habi/tableros-marketing
python3 scripts/build_hub.py
python3 -m pytest scripts/tests/ -q
grep -c "asignacion-co" index.html
```
Expected: pytest en verde, y el `grep` devuelve ≥ 1 (la card aparece en el hub generado).

- [ ] **Step 7: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignacion-co/ index.html
git commit -m "feat(asignacion-co): scaffolding del tablero y pipeline de datos"
```

---

## Task 2: CTE `base` a nivel nid y lente A (cosechas)

**Files:**
- Modify: `asignacion-co/query.sql` (reemplaza el SELECT trivial de la Task 1)

**Interfaces:**
- Consumes: el CTE `leads` de la Task 1.
- Produces: el CTE `base` con estas columnas, que TODAS las tareas siguientes consumen:
  `nid` STRING, `d_creacion` DATE, `fuente` STRING, `area` STRING, `equipo` STRING,
  `d_asig` DATE, `tipo_1` STRING (`gabi`|`comercial`), `tipo_asignacion_1` STRING,
  `d_owner` DATE, `d_primera_asig` DATE, `senal_primera` STRING (`seguimiento`|`owner`),
  `gabi_flag` BOOL, `gabi_producto` STRING, `d_gabi` DATE,
  `prod_1` STRING (`MM`|`INMO`|NULL si nunca entró a ninguno), `d_mm` DATE, `d_inmo` DATE, `d_prod_1` DATE,
  `ts_mm` TIMESTAMP, `ts_inmo` TIMESTAMP, `ts_prod_1` TIMESTAMP (la secuencia se compara con estos, no con las fechas),
  `inmo_despues_de_mm` BOOL, `mm_despues_de_inmo` BOOL,
  `n_asig` INT64, `en_wbr` BOOL.
  Y las métricas de la lente A: `creados`, `asig_30d`, `asig_ever`, `gabi_30d`, `directo_30d`, `prod1_mm`, `prod1_inmo`, `prod1_legacy`.

- [ ] **Step 1: Escribir el CTE `base` completo**

En `asignacion-co/query.sql`, después del CTE `leads`, agregar:

```sql
, asig AS (
  SELECT
    CAST(nid AS STRING) AS nid,
    MIN(DATE(fecha_asignacion)) AS d_asig,
    COUNT(*) AS n_asig,
    ARRAY_AGG(STRUCT(
      LOWER(TRIM(tipo))                                   AS tipo,
      TRIM(tipo_asignacion)                               AS tipo_asignacion,
      COALESCE(NULLIF(TRIM(equipo_inicial), ''), '(sin equipo)') AS equipo
    ) ORDER BY fecha_asignacion LIMIT 1)[OFFSET(0)] AS a1,
    MIN(IF(LOWER(TRIM(tipo)) = 'gabi', DATE(fecha_asignacion), NULL)) AS d_gabi
  FROM `sellers-main-prod.bi_co.seguimiento_asignacion_ibuyer_co`
  WHERE fecha_asignacion IS NOT NULL
    AND DATE(fecha_asignacion) >= DATE_SUB(CURRENT_DATE(), INTERVAL 940 DAY)
  GROUP BY nid
)
, owner AS (
  SELECT CAST(nid AS STRING) AS nid, MIN(DATE(fecha)) AS d_owner
  FROM `sellers-main-prod.hubspot.historical`
  WHERE propiedad = 'hubspot_owner_id'
    AND valor IS NOT NULL AND TRIM(valor) <> ''
    AND DATE(fecha) >= DATE_SUB(CURRENT_DATE(), INTERVAL 940 DAY)
  GROUP BY nid
)
, pipe_ev AS (
  SELECT
    CAST(nid AS STRING) AS nid,
    TIMESTAMP(fecha) AS ts,          -- la secuencia se ordena por TIMESTAMP, no por DATE
    IF(TRIM(valor) = '798578615', 'MM', 'INMO') AS prod
  FROM `sellers-main-prod.hubspot.historical`
  WHERE propiedad = 'pipeline'
    -- SOLO los dos pipelines de producto. 1679217 y los de MX no son productos (ver Global Constraints).
    AND TRIM(valor) IN ('798578615', '803674753')
    AND DATE(fecha) >= DATE_SUB(CURRENT_DATE(), INTERVAL 940 DAY)
)
, pipes AS (
  SELECT
    nid,
    -- Timestamps: son la verdad de la SECUENCIA (1.729 nids tienen MM e INMO el mismo día,
    -- y los 1.769 casos son desempatables con el timestamp)
    MIN(IF(prod = 'MM',   ts, NULL)) AS ts_mm,
    MIN(IF(prod = 'INMO', ts, NULL)) AS ts_inmo,
    MIN(ts)                          AS ts_prod_1,
    ARRAY_AGG(prod ORDER BY ts LIMIT 1)[OFFSET(0)] AS prod_1,
    -- Fechas: derivadas de los timestamps, solo para agrupar por período y medir días
    DATE(MIN(IF(prod = 'MM',   ts, NULL))) AS d_mm,
    DATE(MIN(IF(prod = 'INMO', ts, NULL))) AS d_inmo,
    DATE(MIN(ts))                          AS d_prod_1,
    -- Rutas de regreso: ¿hubo un evento de un producto POSTERIOR a la primera entrada al otro?
    LOGICAL_OR(prod = 'INMO' AND ts > primera_mm)   AS inmo_despues_de_mm,
    LOGICAL_OR(prod = 'MM'   AND ts > primera_inmo) AS mm_despues_de_inmo
  FROM (
    SELECT nid, ts, prod,
           MIN(IF(prod = 'MM',   ts, NULL)) OVER (PARTITION BY nid) AS primera_mm,
           MIN(IF(prod = 'INMO', ts, NULL)) OVER (PARTITION BY nid) AS primera_inmo
    FROM pipe_ev
  )
  GROUP BY nid
)
, gabi AS (
  SELECT CAST(nid AS STRING) AS nid,
         ARRAY_AGG(product_qualified ORDER BY fecha_creacion DESC LIMIT 1)[OFFSET(0)] AS product_qualified
  FROM `sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble`
  WHERE nid IS NOT NULL
  GROUP BY nid
)
, wbr AS (
  SELECT DISTINCT CAST(nid AS STRING) AS nid
  FROM `papyrus-master.sellers_data_mart.sellers_leads_asignados_marketing_wbr_mart`
  WHERE LOWER(pais) = 'colombia'
    AND dia >= DATE_SUB(CURRENT_DATE(), INTERVAL 940 DAY)
)
, base AS (
  SELECT
    l.nid, l.d_creacion, l.fuente_id, l.fuente, l.area,
    COALESCE(a.a1.equipo, '(sin equipo)')                   AS equipo,
    a.d_asig, a.n_asig,
    a.a1.tipo                                               AS tipo_1,
    a.a1.tipo_asignacion                                    AS tipo_asignacion_1,
    o.d_owner,
    LEAST(COALESCE(a.d_asig, DATE '9999-12-31'),
          COALESCE(o.d_owner, DATE '9999-12-31'))           AS d_primera_asig_raw,
    a.d_gabi,
    a.a1.tipo = 'gabi'                                      AS gabi_flag,
    COALESCE(NULLIF(TRIM(g.product_qualified), ''), '(sin calificar)') AS gabi_producto,
    p.prod_1, p.d_prod_1, p.d_mm, p.d_inmo,
    p.ts_mm, p.ts_inmo, p.ts_prod_1, p.inmo_despues_de_mm, p.mm_despues_de_inmo,
    w.nid IS NOT NULL                                       AS en_wbr
  FROM leads l
  LEFT JOIN asig  a USING (nid)
  LEFT JOIN owner o USING (nid)
  LEFT JOIN pipes p USING (nid)
  LEFT JOIN gabi  g USING (nid)
  LEFT JOIN wbr   w USING (nid)
)
, base2 AS (
  SELECT * EXCEPT (d_primera_asig_raw),
    IF(d_primera_asig_raw = DATE '9999-12-31', NULL, d_primera_asig_raw) AS d_primera_asig,
    CASE
      WHEN d_asig IS NULL AND d_owner IS NULL THEN NULL
      WHEN d_owner IS NULL THEN 'seguimiento'
      WHEN d_asig  IS NULL THEN 'owner'
      WHEN d_asig <= d_owner THEN 'seguimiento'
      ELSE 'owner'
    END AS senal_primera
  FROM base
)
```

- [ ] **Step 2: Verificar el `base` con invariantes antes de agregar**

Run (query ad-hoc, no toca el archivo):
```bash
cd ~/habi/tableros-marketing
python3 - <<'PY' > /tmp/chk_base.sql
sql = open('asignacion-co/query.sql').read()
sql = sql.split('SELECT', 1)[0] if False else sql
# corta el SELECT final del archivo y añade el chequeo
cut = sql.rindex('SELECT')
open('/tmp/chk_base.sql','w').write(sql[:cut] + """
SELECT
  COUNT(*) AS nids,
  COUNTIF(d_primera_asig IS NOT NULL) AS asignados,
  COUNTIF(d_primera_asig IS NOT NULL AND d_primera_asig < d_creacion) AS asig_antes_de_crear,
  COUNTIF(d_inmo IS NOT NULL) AS llegaron_inmo,
  COUNTIF(d_mm IS NOT NULL) AS llegaron_mm,
  COUNTIF(d_mm IS NOT NULL AND d_inmo IS NOT NULL AND d_mm < d_inmo) AS mm_antes_inmo,
  COUNTIF(en_wbr) AS en_wbr
FROM base2
""")
PY
bq query --nouse_legacy_sql --format=prettyjson --project_id=sellers-main-prod < /tmp/chk_base.sql
```
Expected:
- `asignados` < `nids` (no todo lead se asigna) y > 0.
- **`asig_antes_de_crear` debe ser 0 o marginal.** Si es alto, hay un problema de zona horaria o de join por `nid`: investigar antes de seguir, no maquillar.
- `mm_antes_inmo` en el orden de magnitud del baseline del spec (8.459 para abr-jul 2026; aquí la ventana es mayor, así que debe ser mayor).
- `en_wbr` < `asignados` (el mart es un subconjunto).

- [ ] **Step 3: Reemplazar el SELECT final por las filas de la lente A**

```sql
, dims AS (
  SELECT nid, 'total'  AS dim, 'total' AS dim_val FROM base2
  UNION ALL SELECT nid, 'fuente', fuente FROM base2
  UNION ALL SELECT nid, 'area',   area   FROM base2
  UNION ALL SELECT nid, 'equipo', equipo FROM base2
)
, lente_a AS (
  SELECT
    b.d_creacion AS d, x.dim, x.dim_val,
    COUNT(DISTINCT b.nid) AS creados,
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL
                      AND DATE_DIFF(b.d_primera_asig, b.d_creacion, DAY) <= 30, b.nid, NULL)) AS asig_30d,
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL, b.nid, NULL))                             AS asig_ever,
    COUNT(DISTINCT IF(b.gabi_flag
                      AND DATE_DIFF(b.d_asig, b.d_creacion, DAY) <= 30, b.nid, NULL))         AS gabi_30d,
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL AND NOT COALESCE(b.gabi_flag, FALSE)
                      AND DATE_DIFF(b.d_primera_asig, b.d_creacion, DAY) <= 30, b.nid, NULL)) AS directo_30d,
    -- Producto: solo MM/INMO, y SIEMPRE condicionado a estar asignado
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL AND b.prod_1 = 'MM'
                      AND DATE_DIFF(b.d_prod_1, b.d_creacion, DAY) <= 30, b.nid, NULL))       AS prod1_mm,
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL AND b.prod_1 = 'INMO'
                      AND DATE_DIFF(b.d_prod_1, b.d_creacion, DAY) <= 30, b.nid, NULL))       AS prod1_inmo,
    -- Asignados que nunca entraron a MM ni INMO (dentro de la ventana de 30 d)
    COUNT(DISTINCT IF(b.d_primera_asig IS NOT NULL AND b.prod_1 IS NULL
                      AND DATE_DIFF(b.d_primera_asig, b.d_creacion, DAY) <= 30, b.nid, NULL)) AS sin_producto
  FROM base2 b
  JOIN dims x USING (nid)
  GROUP BY d, dim, dim_val
)
SELECT 'count' AS kind, 'A' AS lente, d, dim, dim_val, metrica, n
FROM lente_a
UNPIVOT (n FOR metrica IN (
  creados, asig_30d, asig_ever, gabi_30d, directo_30d, prod1_mm, prod1_inmo, sin_producto
))
WHERE n > 0
```

- [ ] **Step 4: Correr y verificar invariantes de la lente A**

Run:
```bash
cd ~/habi/tableros-marketing
bq query --nouse_legacy_sql --dry_run --format=none --project_id=sellers-main-prod < asignacion-co/query.sql
python3 scripts/run_queries.py --only asignacion-co
python3 - <<'PY'
import json, collections
r = json.load(open('asignacion-co/data.json'))
tot = collections.defaultdict(int)
for x in r:
    if x['dim'] == 'total':
        tot[x['metrica']] += int(x['n'])
print(dict(tot))
assert tot['asig_30d'] <= tot['asig_ever'] <= tot['creados'], 'jerarquía de asignados rota'
assert tot['gabi_30d'] + tot['directo_30d'] == tot['asig_30d'], 'gabi y directo deben particionar asig_30d exactamente'
assert tot['prod1_mm'] + tot['prod1_inmo'] + tot['sin_producto'] <= tot['asig_ever'], 'productos exceden asignados'
# la suma por dimensión debe reproducir el total (± leads sin ese atributo)
for dim in ('fuente','area','equipo'):
    s = sum(int(x['n']) for x in r if x['dim']==dim and x['metrica']=='creados')
    assert s == tot['creados'], f'{dim}: {s} != {tot["creados"]}'
print('OK')
PY
```
Expected: dry-run válido, y `OK` en todos los asserts. Si la suma por dimensión no cuadra, es que un `COALESCE` de la dimensión quedó suelto y hay nulos escapándose.

- [ ] **Step 5: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignacion-co/query.sql asignacion-co/data.json
git commit -m "feat(asignacion-co): CTE base a nivel nid y filas de la lente A"
```

---

## Task 3: Lentes B y C (rutas de llegada a cada producto)

**Files:**
- Modify: `asignacion-co/query.sql`

**Interfaces:**
- Consumes: `base2` de la Task 2.
- Produces: filas `kind='count'` con `lente='B'` (ancla `d_inmo`) y `lente='C'` (ancla `d_mm`), con `metrica` ∈ `llegadas`, `r_directo`, `r_gabi_prod`, `r_gabi_mm_cruce`, `r_cruce`, `r_regreso`.

- [ ] **Step 1: Definir la taxonomía de rutas como CTE, con prioridad explícita**

Agregar antes del SELECT final:

```sql
-- Rutas de llegada a INMO. El CASE es EXCLUYENTE y el orden importa:
--   1) regreso   : ya había estado en INMO, pasó por MM y volvió
--   2) gabi_mm   : GABI lo tomó y su calificación actual es de MM (ibuyer*), y pasó por MM antes de INMO
--   3) cruce     : pasó por MM antes de INMO (resto, incluye GABI con real_estate/transient/sin calificar)
--   4) gabi_prod : GABI lo tomó y NO pasó por MM antes
--   5) directo   : ni GABI ni MM previo
, rutas_inmo AS (
  SELECT b.*, CASE
    WHEN b.d_inmo IS NULL THEN NULL
    WHEN b.prod_1 = 'INMO' AND b.ts_mm IS NOT NULL AND b.ts_mm > b.ts_inmo
         AND b.inmo_despues_de_mm                                   THEN 'r_regreso'
    WHEN b.ts_mm IS NOT NULL AND b.ts_mm < b.ts_inmo
         AND COALESCE(b.gabi_flag, FALSE)
         AND b.gabi_producto IN ('ibuyer', 'ibuyer_and_real_estate') THEN 'r_gabi_mm_cruce'
    WHEN b.ts_mm IS NOT NULL AND b.ts_mm < b.ts_inmo                    THEN 'r_cruce'
    WHEN COALESCE(b.gabi_flag, FALSE)                                THEN 'r_gabi_prod'
    ELSE 'r_directo' END AS ruta
  FROM base2 b
)
-- Rutas de llegada a MM: espejo exacto, cambiando INMO <-> MM y la calificación de GABI
, rutas_mm AS (
  SELECT b.*, CASE
    WHEN b.d_mm IS NULL THEN NULL
    WHEN b.prod_1 = 'MM' AND b.mm_despues_de_inmo                    THEN 'r_regreso'
    WHEN b.ts_inmo IS NOT NULL AND b.ts_inmo < b.ts_mm
         AND COALESCE(b.gabi_flag, FALSE)
         AND b.gabi_producto IN ('real_estate', 'ibuyer_and_real_estate') THEN 'r_gabi_mm_cruce'
    WHEN b.ts_inmo IS NOT NULL AND b.ts_inmo < b.ts_mm                  THEN 'r_cruce'
    WHEN COALESCE(b.gabi_flag, FALSE)                                THEN 'r_gabi_prod'
    ELSE 'r_directo' END AS ruta
  FROM base2 b
)
```

⚠️ `r_regreso` se apoya en `inmo_despues_de_mm` / `mm_despues_de_inmo` del CTE `pipes` (Task 2), **no** en comparar solo las primeras entradas: "MM primero y luego INMO" no es un regreso, es un cruce simple. Si esas dos columnas no existen en `pipes`, volver a la Task 2 antes de seguir.

- [ ] **Step 2: Emitir las filas de B y C**

Reemplazar el `SELECT` final por un `UNION ALL` que agregue, después del bloque de la lente A:

```sql
UNION ALL
SELECT 'count', 'B', r.d_inmo, x.dim, x.dim_val, m.metrica, m.n
FROM (
  SELECT d_inmo, dim, dim_val,
         COUNT(DISTINCT nid) AS llegadas,
         COUNT(DISTINCT IF(ruta='r_directo',       nid, NULL)) AS r_directo,
         COUNT(DISTINCT IF(ruta='r_gabi_prod',     nid, NULL)) AS r_gabi_prod,
         COUNT(DISTINCT IF(ruta='r_gabi_mm_cruce', nid, NULL)) AS r_gabi_mm_cruce,
         COUNT(DISTINCT IF(ruta='r_cruce',         nid, NULL)) AS r_cruce,
         COUNT(DISTINCT IF(ruta='r_regreso',       nid, NULL)) AS r_regreso
  FROM rutas_inmo JOIN dims USING (nid)
  WHERE d_inmo IS NOT NULL
  GROUP BY d_inmo, dim, dim_val
) r
UNPIVOT (n FOR metrica IN (llegadas, r_directo, r_gabi_prod, r_gabi_mm_cruce, r_cruce, r_regreso)) m
CROSS JOIN UNNEST([STRUCT(r.dim AS dim, r.dim_val AS dim_val)]) x
WHERE m.n > 0
```

(y el bloque equivalente para `lente='C'` con `rutas_mm` y ancla `d_mm`).

- [ ] **Step 3: Verificar que las rutas particionan las llegadas**

Run:
```bash
cd ~/habi/tableros-marketing
python3 scripts/run_queries.py --only asignacion-co
python3 - <<'PY'
import json, collections
r = json.load(open('asignacion-co/data.json'))
for lente in ('B','C'):
    t = collections.defaultdict(int)
    for x in r:
        if x['lente']==lente and x['dim']=='total': t[x['metrica']] += int(x['n'])
    rutas = sum(v for k,v in t.items() if k.startswith('r_'))
    print(lente, dict(t), 'suma rutas', rutas)
    assert rutas == t['llegadas'], f'{lente}: rutas {rutas} != llegadas {t["llegadas"]}'
print('OK')
PY
```
Expected: para cada lente, la suma de las 5 rutas es **exactamente** igual a `llegadas` (el CASE es excluyente y exhaustivo). Si no cuadra, hay una rama del CASE que devuelve NULL para casos con `d_inmo`/`d_mm` no nulo.

- [ ] **Step 4: Contrastar con el baseline del spec**

Run:
```bash
cd ~/habi/tableros-marketing
python3 - <<'PY'
import json, collections
r = json.load(open('asignacion-co/data.json'))
# ventana abr-jul 2026 del baseline: MM->INMO = 8.459 (mediana 10 d, p90 52 d)
s = sum(int(x['n']) for x in r
        if x['lente']=='B' and x['dim']=='total'
        and x['metrica'] in ('r_cruce','r_gabi_mm_cruce')
        and '2026-04-01' <= x['d'] <= '2026-07-31')
print('MM->INMO con llegada en abr-jul 2026:', s)
# ⚠️ Baseline recalibrado (verificado 2026-08-04). El baseline original de 8.459 se midió con
# una ventana de eventos de 4 meses, así que solo veía cruces cuyo paso por MM también cayó
# en abr-jul. Aquí la ventana de `pipes` es de 940 días, así que el total es ~2x: ~16.2k-16.6k,
# de los cuales ~8.3k tienen su paso por MM dentro de abr-2026 (esos SÍ son comparables al
# baseline) y ~8.0k lo tienen antes. Medición independiente del controlador: 16.572 / 8.302 / 8.270.
assert 14000 <= s <= 19000, f'total de cruces fuera del rango esperado ({s}): revisar la definición de cruce'
PY
```
Expected: un valor cercano a 8.459. **Si se aleja más de ~20%, parar y explicar la diferencia** — puede ser legítima (la ventana de `pipes` es más larga aquí, así que capta cruces cuyo paso por MM fue antes de abril) pero hay que entenderla, no asumirla.

- [ ] **Step 5: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignacion-co/query.sql asignacion-co/data.json
git commit -m "feat(asignacion-co): lentes B y C con la taxonomía de rutas de llegada"
```

---

## Task 4: Tiempos por salto (pre-agregados) y reconciliación con el WBR mart

**Files:**
- Modify: `asignacion-co/query.sql`

**Interfaces:**
- Consumes: `base2`, `rutas_inmo`, `rutas_mm`.
- Produces: filas `kind='tiempo'` `{kind, gran, periodo, salto, mediana, p90, n}` y filas `kind='count'` con `lente='REC'`, `metrica` ∈ `q_asig_en_mart`, `q_asig_no_mart`, `q_noasig_en_mart`, `q_noasig_no_mart`, `gap_no_marketing`, `gap_ventanas`, `gap_sin_explicar`.

**Enmienda al spec:** las medianas y p90 **no son re-agregables** desde grano diario, así que se pre-calculan aquí para las 3 granularidades (`semana`, `mes`, `ciclo`) en vez de dejar que el frontend las derive.

- [ ] **Step 1: Emitir los tiempos por salto en las 3 granularidades**

```sql
UNION ALL
SELECT 'tiempo' AS kind, gran, CAST(periodo AS STRING) AS periodo, salto,
       CAST(mediana AS STRING) AS mediana, CAST(p90 AS STRING) AS p90, CAST(n AS STRING) AS n
FROM (
  SELECT gran, periodo, salto,
         APPROX_QUANTILES(dias, 100)[OFFSET(50)] AS mediana,
         APPROX_QUANTILES(dias, 100)[OFFSET(90)] AS p90,
         COUNT(*) AS n
  FROM (
    SELECT g.gran,
           CASE g.gran
             WHEN 'semana' THEN DATE_TRUNC(s.d_ancla, ISOWEEK)
             WHEN 'mes'    THEN DATE_TRUNC(s.d_ancla, MONTH)
             ELSE               DATE_TRUNC(s.d_ancla, WEEK(WEDNESDAY))
           END AS periodo,
           s.salto, s.dias
    FROM (
      SELECT 'creacion_gabi' AS salto, d_gabi AS d_ancla, DATE_DIFF(d_gabi, d_creacion, DAY) AS dias
        FROM base2 WHERE d_gabi IS NOT NULL
      UNION ALL
      SELECT 'gabi_mm',       d_mm,   DATE_DIFF(d_mm,   d_gabi, DAY)
        FROM base2 WHERE d_gabi IS NOT NULL AND d_mm   IS NOT NULL AND d_mm   >= d_gabi
      UNION ALL
      SELECT 'mm_inmo',       d_inmo, DATE_DIFF(d_inmo, d_mm,   DAY)
        FROM base2 WHERE d_mm   IS NOT NULL AND d_inmo IS NOT NULL AND d_inmo >  d_mm
      UNION ALL
      SELECT 'inmo_mm',       d_mm,   DATE_DIFF(d_mm,   d_inmo, DAY)
        FROM base2 WHERE d_inmo IS NOT NULL AND d_mm   IS NOT NULL AND d_mm   >  d_inmo
    ) s
    CROSS JOIN UNNEST(['semana','mes','ciclo']) AS gran WITH OFFSET
  )
  GROUP BY gran, periodo, salto
)
```

⚠️ El `CROSS JOIN UNNEST(...) AS gran WITH OFFSET` necesita alias de struct: usar `CROSS JOIN UNNEST(['semana','mes','ciclo']) AS gran` y referenciarlo como `gran` (sin `g.`). Ajustar las referencias `g.gran` → `gran` al escribirlo.

- [ ] **Step 2: Emitir los cuadrantes y la descomposición del gap**

Las fuentes de marketing del WBR en CO, tal como las usa el tablero `asignados-creacion`: WEB(3), Leadforms(47,37,41,42), Habimetro(7), CRM(20), Brokers(39), Comercial(35). `Ventana` es `fuente_id = 1` y **siempre se excluye** del mart.

`fuente_id` ya viene propagado desde `leads` hasta `base2` (Tasks 1 y 2), así que la clasificación del gap se hace directo sobre él.

```sql
UNION ALL
SELECT 'count', 'REC', d_creacion, 'total', 'total', metrica, n
FROM (
  SELECT d_creacion,
    COUNT(DISTINCT IF(    asignado AND     en_wbr, nid, NULL)) AS q_asig_en_mart,
    COUNT(DISTINCT IF(    asignado AND NOT en_wbr, nid, NULL)) AS q_asig_no_mart,
    COUNT(DISTINCT IF(NOT asignado AND     en_wbr, nid, NULL)) AS q_noasig_en_mart,
    COUNT(DISTINCT IF(NOT asignado AND NOT en_wbr, nid, NULL)) AS q_noasig_no_mart,
    -- descomposición del cuadrante ⚠ "asignado y NO en el mart", por prioridad
    -- ⚠️ COALESCE obligatorio: con fuente_id NULL las tres condiciones evalúan a NULL (no a FALSE)
    -- y el lead se cae de los tres buckets, rompiendo la exhaustividad. Verificado: 41 leads así.
    -- Un fuente_id nulo no es fuente de marketing → cae en gap_no_marketing.
    COUNT(DISTINCT IF(asignado AND NOT en_wbr AND COALESCE(fuente_id, -1) = 1,  nid, NULL)) AS gap_ventanas,
    COUNT(DISTINCT IF(asignado AND NOT en_wbr AND COALESCE(fuente_id, -1) <> 1
                      AND COALESCE(fuente_id, -1) NOT IN (3,47,37,41,42,7,20,39,35), nid, NULL)) AS gap_no_marketing,
    COUNT(DISTINCT IF(asignado AND NOT en_wbr
                      AND COALESCE(fuente_id, -1) IN (3,47,37,41,42,7,20,39,35),      nid, NULL)) AS gap_sin_explicar
  FROM (SELECT *, d_primera_asig IS NOT NULL AS asignado FROM base2)
  GROUP BY d_creacion
)
UNPIVOT (n FOR metrica IN (
  q_asig_en_mart, q_asig_no_mart, q_noasig_en_mart, q_noasig_no_mart,
  gap_ventanas, gap_no_marketing, gap_sin_explicar
))
WHERE n > 0
```

- [ ] **Step 3: Verificar los cuadrantes y el gap**

Run:
```bash
cd ~/habi/tableros-marketing
bq query --nouse_legacy_sql --dry_run --format=none --project_id=sellers-main-prod < asignacion-co/query.sql
python3 scripts/run_queries.py --only asignacion-co
python3 - <<'PY'
import json, collections
r = json.load(open('asignacion-co/data.json'))
t = collections.defaultdict(int)
for x in r:
    if x['lente']=='REC': t[x['metrica']] += int(x['n'])
creados = sum(int(x['n']) for x in r if x['lente']=='A' and x['dim']=='total' and x['metrica']=='creados')
quad = t['q_asig_en_mart']+t['q_asig_no_mart']+t['q_noasig_en_mart']+t['q_noasig_no_mart']
gap  = t['gap_ventanas']+t['gap_no_marketing']+t['gap_sin_explicar']
print(dict(t)); print('cuadrantes', quad, 'creados', creados, 'gap', gap)
assert quad == creados, 'los 4 cuadrantes deben sumar el universo de creados'
assert gap == t['q_asig_no_mart'], 'la descomposición debe cubrir todo el cuadrante del gap'
tiempos = [x for x in r if x.get('kind')=='tiempo']
assert tiempos, 'no se emitieron filas de tiempo'
assert {x['gran'] for x in tiempos} == {'semana','mes','ciclo'}
print('filas tiempo', len(tiempos), 'OK')
PY
```
Expected: los 4 cuadrantes suman exactamente los creados; la descomposición cubre el cuadrante del gap; hay filas de tiempo en las 3 granularidades.

- [ ] **Step 4: Anotar el tamaño de `gap_sin_explicar` para el bloque de Conclusiones**

Run:
```bash
cd ~/habi/tableros-marketing
python3 - <<'PY'
import json, collections
r = json.load(open('asignacion-co/data.json'))
por_mes = collections.defaultdict(lambda: collections.defaultdict(int))
for x in r:
    if x['lente']=='REC': por_mes[x['d'][:7]][x['metrica']] += int(x['n'])
for m in sorted(por_mes)[-6:]:
    d = por_mes[m]
    print(m, 'asig_no_mart', d['q_asig_no_mart'], 'sin_explicar', d['gap_sin_explicar'],
          'noasig_en_mart', d['q_noasig_en_mart'])
PY
```
Expected: una tabla de 6 meses. **Guardar esta salida** — es la evidencia del bloque de Conclusiones de la Task 7. `q_noasig_en_mart` > 0 significa que el mart cuenta como asignados leads que nuestras dos señales no ven: ese es el hallazgo más importante del proyecto y hay que reportarlo con su tamaño, no con adjetivos.

- [ ] **Step 5: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignacion-co/query.sql asignacion-co/data.json
git commit -m "feat(asignacion-co): tiempos por salto y reconciliación con el WBR mart"
```

---

## Task 5: Frontend — selectores y lente A

**Files:**
- Modify: `asignacion-co/index.html`

**Interfaces:**
- Consumes: `data.json` (contrato de la sección File Structure).
- Produces: funciones JS que las Tasks 6-7 reutilizan:
  - `bucket(dateStr, gran)` → STRING clave de período (`'2026-W31'` | `'2026-08'` | `'2026-C31'`)
  - `ultimosPeriodos(rows, gran, n=20)` → array de claves de período, ascendente
  - `agrega(rows, {lente, gran, dim, dimVal})` → `Map<periodo, Map<metrica, number>>`
  - `esInmaduro(periodo, gran, dias)` → BOOL

- [ ] **Step 1: Escribir los helpers de bucketing y agregación**

En el `<script>` de `asignacion-co/index.html`:

```javascript
const D = s => new Date(s + 'T00:00:00Z');

function isoWeekKey(dt) {
  const t = new Date(Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth(), dt.getUTCDate()));
  const dow = (t.getUTCDay() + 6) % 7;             // lunes = 0
  t.setUTCDate(t.getUTCDate() - dow + 3);          // jueves de esa semana ISO
  const y = t.getUTCFullYear();
  const wk = 1 + Math.round((t - Date.UTC(y, 0, 4)) / 604800000);
  return `${y}-W${String(wk).padStart(2, '0')}`;
}

// Ciclo comercial: semanas que arrancan el miércoles
function cicloKey(dt) {
  const t = new Date(dt.getTime());
  const shift = (t.getUTCDay() - 3 + 7) % 7;       // miércoles = 3
  t.setUTCDate(t.getUTCDate() - shift);
  return `${t.toISOString().slice(0, 10)}`;
}

function bucket(s, gran) {
  const dt = D(s);
  if (gran === 'mes')   return s.slice(0, 7);
  if (gran === 'ciclo') return cicloKey(dt);
  return isoWeekKey(dt);
}

function ultimosPeriodos(rows, gran, n = 20) {
  const set = new Set(rows.map(r => bucket(r.d, gran)));
  return [...set].sort().slice(-n);
}

function agrega(rows, { lente, gran, dim, dimVal }) {
  const out = new Map();
  for (const r of rows) {
    if (r.kind !== 'count' || r.lente !== lente) continue;
    if (r.dim !== dim || r.dim_val !== dimVal) continue;
    const p = bucket(r.d, gran);
    if (!out.has(p)) out.set(p, new Map());
    const m = out.get(p);
    m.set(r.metrica, (m.get(r.metrica) || 0) + Number(r.n));   // bq devuelve STRING
  }
  return out;
}

// Último día del período, según la granularidad
function finDePeriodo(periodo, gran) {
  if (gran === 'mes') {
    const [y, m] = periodo.split('-').map(Number);
    return new Date(Date.UTC(y, m, 0));               // día 0 del mes siguiente = último del mes
  }
  if (gran === 'ciclo') {
    const t = D(periodo);                             // miércoles de inicio
    t.setUTCDate(t.getUTCDate() + 6);                 // martes de cierre
    return t;
  }
  const [y, w] = periodo.split('-W').map(Number);     // semana ISO -> domingo
  const jue = new Date(Date.UTC(y, 0, 4));
  const lun = new Date(jue);
  lun.setUTCDate(jue.getUTCDate() - ((jue.getUTCDay() + 6) % 7) + (w - 1) * 7);
  lun.setUTCDate(lun.getUTCDate() + 6);
  return lun;
}

// Un período está inmaduro si su último día aún no cumple `dias` desde hoy
function esInmaduro(periodo, gran, dias) {
  const fin = finDePeriodo(periodo, gran);
  return (Date.now() - fin.getTime()) / 86400000 < dias;
}
```

- [ ] **Step 2: Verificar los helpers con casos concretos en el navegador**

Run:
```bash
cd ~/habi/tableros-marketing
python3 -m http.server 8091 >/dev/null 2>&1 &
sleep 1 && echo "abrir http://localhost:8091/asignacion-co/"
```

En la consola del navegador, ejecutar y comparar:
```javascript
bucket('2026-08-04','mes')    // '2026-08'
bucket('2026-08-04','semana') // '2026-W32'  (martes de la semana ISO 32)
bucket('2026-08-04','ciclo')  // '2026-07-29' (miércoles anterior)
esInmaduro('2026-08','mes',30) // true
esInmaduro('2026-01','mes',30) // false
```
Expected: los 5 valores exactos. Si `isoWeekKey` da la semana corrida, revisar el ajuste al jueves.

- [ ] **Step 3: Construir los dos selectores globales**

Ambos arriba, fuera de los bloques de lente, y al cambiar cualquiera se redibujan las tres lentes.

1. **Granularidad** — 3 chips: `Semana` · `Mes` (default) · `Ciclo mié-mar`. Guardan `granActual` y llaman a `render()`.
2. **Filtro** — el **selector estándar de chips + grupos** del repo: un grupo por dimensión (`Fuente`, `Área metropolitana`, `Equipo`) con sus valores como chips, **uno activo a la vez** más un chip `Todos` (que corresponde a `dim='total', dim_val='total'`). Los valores se derivan del `data.json` en carga:

```javascript
function valoresPorDim(rows) {
  const out = { fuente: new Set(), area: new Set(), equipo: new Set() };
  for (const r of rows) if (r.kind === 'count' && out[r.dim]) out[r.dim].add(r.dim_val);
  return Object.fromEntries(Object.entries(out).map(([k, v]) => [k, [...v].sort()]));
}
```

El estado del filtro es `{dim, dimVal}` y se pasa tal cual a `agrega()`. Default: `{dim:'total', dimVal:'total'}`.

- [ ] **Step 4: Renderizar la tabla de la lente A**

Columnas, en este orden: `Cosecha` · `Creados` · `Asignado ≤30d` · `Ever asignado (ref.)` · `GABI` · `Directo a pipeline` · `1er producto MM` · `INMO` · `Sin producto`.

**Regla de cobertura:** en los períodos cuyo fin sea anterior a **2025-09-18** (MM) / **2025-10-02** (INMO), las tres columnas de producto se renderizan como `—` con `title="los pipelines MM/INMO no existían aún"`, NUNCA como 0. Las columnas de asignación se muestran normal. Debajo de la tabla, una nota: "Las columnas de producto arrancan en sep-2025, cuando se crearon los pipelines MM e INMO en HubSpot".

Reglas de render:
- Cada celda de métrica muestra `n (%)`. El **denominador del % es `asig_30d`**, salvo `Asignado ≤30d` y `Ever asignado`, cuyo denominador es `creados`.
- Heatmap en el % por fila (escala roja → verde según min/max de la columna).
- Si `esInmaduro(periodo, granActual, 30)` es true, la fila se pinta atenuada (`opacity: .55`) y lleva el label `inmadura` junto a la cosecha (30 d = la ventana de L1/L2/L3).
- El subtítulo del bloque dice literalmente: **"Ancla: fecha de creación del lead. Denominador de los %: asignados ≤30d."**

- [ ] **Step 5: Agregar la gráfica de la lente A con `mkChart`**

Un `<canvas>` dentro de `.panel > .ch`, con tres series de líneas: `% asig_30d / creados`, `% prod1_mm / asig_30d`, `% prod1_inmo / asig_30d`. Usar `mkChart(id, labels, data, {type:'line', pct:true})`. Marcar visualmente el corte de **abril 2026** (cambio de lógica de asignación) con una anotación o un cambio de estilo de línea en ese punto.

- [ ] **Step 6: Revisar en localhost y verificar contra los datos**

Run:
```bash
cd ~/habi/tableros-marketing
python3 - <<'PY'
import json, collections
r = json.load(open('asignacion-co/data.json'))
t = collections.defaultdict(int)
for x in r:
    if x['lente']=='A' and x['dim']=='total' and x['d'][:7]=='2026-06': t[x['metrica']] += int(x['n'])
print('junio 2026:', dict(t))
PY
```
Expected: los números impresos coinciden **exactamente** con la fila de junio 2026 en la tabla del navegador (granularidad `mes`). Si no, el bucketing del frontend está mal.

- [ ] **Step 7: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignacion-co/index.html
git commit -m "feat(asignacion-co): selectores de granularidad y filtros + lente A"
```

---

## Task 6: Frontend — lentes B y C

**Files:**
- Modify: `asignacion-co/index.html`

**Interfaces:**
- Consumes: `bucket`, `ultimosPeriodos`, `agrega` de la Task 5; filas `lente='B'|'C'` y `kind='tiempo'`.
- Produces: nada nuevo que otras tareas consuman.

- [ ] **Step 1: Renderizar la tabla de rutas de la lente B**

Columnas: `Período` · `Llegadas INMO` · `Directo` · `GABI → INMO` · `GABI(MM) → MM → INMO` · `MM → INMO` · `INMO → MM → INMO`.

Mapeo de métrica a columna: `llegadas`, `r_directo`, `r_gabi_prod`, `r_gabi_mm_cruce`, `r_cruce`, `r_regreso`. Cada celda `n (%)` con denominador `llegadas`.

Subtítulo literal: **"Ancla: fecha de llegada a INMO. Este período NO es el mismo grupo de leads que la lente A."** Con el mismo peso tipográfico que el título del bloque, no como nota al pie.

- [ ] **Step 2: Renderizar el panel de tiempos por salto**

Leer las filas `kind='tiempo'` filtrando por la granularidad seleccionada. Tabla con `Período` · `creación → GABI` · `GABI → MM` · `MM → INMO`, y cada celda mostrando `mediana d (p90 d)`. Rotular la cabecera del panel: **"mediana (p90) en días — nunca promedio"**.

- [ ] **Step 3: Renderizar la lente C como espejo**

Misma estructura con `lente='C'`, ancla `d_mm`, y el salto `inmo_mm` en el panel de tiempos. Columnas: `Directo` · `GABI → MM` · `GABI(INMO) → INMO → MM` · `INMO → MM` · `re-entrada a MM`.

- [ ] **Step 4: Agregar la advertencia de `product_qualified`**

Debajo de las columnas que usan la calificación de GABI (`r_gabi_mm_cruce` en B y C), un callout con este texto exacto:

> `product_qualified` no tiene fecha ni historial: es el **estado actual** de la calificación de GABI. Estas columnas dicen "hoy está calificado así y pasó por el otro producto", **no** que la calificación fuera anterior al paso.

- [ ] **Step 5: Verificar que las rutas suman en pantalla**

Run:
```bash
cd ~/habi/tableros-marketing
python3 - <<'PY'
import json, collections
r = json.load(open('asignacion-co/data.json'))
for lente in ('B','C'):
    t = collections.defaultdict(int)
    for x in r:
        if x['lente']==lente and x['dim']=='total' and x['d'][:7]=='2026-06': t[x['metrica']]+=int(x['n'])
    rutas = sum(v for k,v in t.items() if k.startswith('r_'))
    print(lente,'junio:',dict(t),'suma rutas',rutas)
PY
```
Expected: en el navegador (granularidad `mes`, fila junio 2026), la suma de las 5 columnas de ruta es igual a `Llegadas`, y coincide con esta salida.

- [ ] **Step 6: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignacion-co/index.html
git commit -m "feat(asignacion-co): lentes B y C con rutas y tiempos por salto"
```

---

## Task 7: Bloque de Conclusiones (reconciliación WBR)

**Files:**
- Modify: `asignacion-co/index.html`

**Interfaces:**
- Consumes: filas `lente='REC'`; la salida guardada en la Task 4 Step 4.
- Produces: nada.

- [ ] **Step 1: Renderizar la matriz de cuadrantes**

Tabla 2×2 con los 4 cuadrantes (`q_asig_en_mart`, `q_asig_no_mart`, `q_noasig_en_mart`, `q_noasig_no_mart`) para los últimos 20 períodos de la granularidad seleccionada, marcando en ámbar los dos cuadrantes de desacuerdo.

- [ ] **Step 2: Renderizar la descomposición del gap**

Barras apiladas con `mkChart` (`type:'bar'`) sobre `gap_ventanas`, `gap_no_marketing`, `gap_sin_explicar`, por período. `gap_sin_explicar` en el color de alerta.

- [ ] **Step 3: Escribir el texto de conclusiones con las cifras reales**

Redactar el bloque usando los números que salieron en la Task 4 Step 4 (no inventar ninguno). Debe contener, en este orden:

1. **La premisa corregida:** ever-asignado y el WBR mart no pueden coincidir por construcción — el mart es un indicador de marketing con 16 filtros, el ever-asignado cuenta todo lo asignado. Las dos brechas (esperada vs no esperada) van separadas explícitamente.
2. **El tamaño de cada brecha** con las cifras de los últimos 6 meses.
3. **El hallazgo accionable:** qué hay en `gap_sin_explicar` (leads de fuente de marketing, asignados, ausentes del mart) y en `q_noasig_en_mart` (el mart los cuenta y nuestras señales no).
4. **La propuesta de mejora**, con dos ítems concretos: (a) qué revisar en la construcción del mart según lo que domine el gap; (b) **instrumentar `product_qualified` en el historial de HubSpot**, sin lo cual la ruta GABI→producto no es fechable.

Reglas de redacción: sin jerga técnica en el texto visible, framing factual, y **ninguna afirmación sin su cifra al lado**.

- [ ] **Step 4: Verificar que las cifras del texto coinciden con el JSON**

Run:
```bash
cd ~/habi/tableros-marketing
grep -oE '[0-9]{3,}' asignacion-co/index.html | sort -u | head -30
python3 - <<'PY'
import json, collections
r = json.load(open('asignacion-co/data.json'))
t = collections.defaultdict(int)
for x in r:
    if x['lente']=='REC': t[x['metrica']] += int(x['n'])
print({k:v for k,v in t.items()})
PY
```
Expected: cada cifra citada en el texto de conclusiones aparece en la salida del JSON. Cualquier número en el HTML que no se pueda rastrear al `data.json` es un error y hay que quitarlo.

- [ ] **Step 5: Commit**

```bash
cd ~/habi/tableros-marketing
git add asignacion-co/index.html
git commit -m "feat(asignacion-co): bloque de conclusiones con la reconciliación del WBR mart"
```

---

## Task 8: Revisión final, hub y publicación

**Files:**
- Modify: `index.html` (raíz, **generado** — solo vía `build_hub.py`)

- [ ] **Step 1: Revisar el tablero completo en localhost**

Run:
```bash
cd ~/habi/tableros-marketing
python3 -m http.server 8091 >/dev/null 2>&1 &
sleep 1 && echo "abrir http://localhost:8091/asignacion-co/"
```

Checklist visual: los 3 selectores de granularidad cambian las 3 lentes a la vez · cada bloque muestra su ancla y su denominador en el subtítulo · 20 períodos por lente · filas inmaduras atenuadas · el corte de abril 2026 visible en la gráfica de A · tema claro y oscuro legibles.

- [ ] **Step 2: Regenerar el hub y correr los tests del generador**

Run:
```bash
cd ~/habi/tableros-marketing
python3 scripts/build_hub.py
python3 -m pytest scripts/tests/ -q
```
Expected: pytest en verde y la card `Asignación · MM vs INMO (CO)` presente en `index.html` de la raíz.

- [ ] **Step 3: Confirmar el costo del job en el cron**

Run:
```bash
cd ~/habi/tableros-marketing
bq query --nouse_legacy_sql --dry_run --format=none --project_id=sellers-main-prod < asignacion-co/query.sql
```
Expected: upper bound **< 5 GB** (el `maximum_bytes_billed` del `meta.json`). Si se pasa, partir el query en dos y usar un `build.py` en la carpeta, siguiendo el patrón de `funnel-web-mx`.

- [ ] **Step 4: Esperar el visto bueno de Camilo antes de pushear**

**No pushear sin revisión.** El flujo del repo es: revisar en `localhost:8091` → visto bueno → push. Presentar el tablero y esperar respuesta.

- [ ] **Step 5: Commit y push**

```bash
cd ~/habi/tableros-marketing
git add asignacion-co/ index.html
git commit -m "feat(asignacion-co): tablero de seguimiento de asignación MM vs INMO"
git pull --rebase -q && git push
```

---

## Notas de riesgo para quien ejecute

- **`hubspot.historical` es la tabla caliente del plan.** Si algún paso se pasa de bytes, el culpable casi siempre es un CTE sobre `historical` sin filtro de `propiedad` o sin filtro de `fecha`. Los dos filtros son obligatorios: la tabla está particionada por mes en `fecha` y clusterizada por `propiedad`.
- **`bq --format=json` devuelve strings.** Todo `Number()` omitido en el frontend produce concatenaciones silenciosas (`"12" + "5" = "125"`). Si un total se ve absurdamente grande, es esto.
- **No "arreglar" invariantes que fallan ajustando el assert.** Si `asig_antes_de_crear` sale alto o las rutas no suman, hay un problema real de datos o de definición: reportarlo.
- **El baseline de 8.459 (MM→INMO abr-jul 2026) es el ancla de confianza del proyecto.** Si el número final se aleja mucho y no hay explicación, algo está mal en la taxonomía de rutas.
