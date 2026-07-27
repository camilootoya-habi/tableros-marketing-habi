# Tablero: entrega desde Neon — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El tablero incorpora la entrega persistida en Neon (`send_log`) como 3ª fuente de `mbm`, durable y sin lag, para no volver a tener huecos tipo 22-jul en cosecha/errores/A/B.

**Architecture:** `sources_neon.delivery_by_msgid` (query + helper puro) → `agg.merge_neon_delivery` (merge puro con precedencia) → `build_data.py` lo aplica tras el merge de Infobip. Read-rate (`seen`) intacto (del mart).

**Tech Stack:** Python 3.12, pytest, psycopg. Sin dependencias nuevas.

## Global Constraints

- `error_name` de Neon se formatea `f"{error_name} (code {error_id})"` (o `"No Error (code 0)"` si error_id ∈ {None,0}) para que `agg.err_bucket` lo parsee igual que mart/Infobip.
- Merge (precedencia): Neon **rellena** lo ausente y **pisa con estado terminal** (delivered/undeliverable/rejected); **nunca regresa** un terminal a pending; **preserva `seen`** de `mbm` (Neon no trae `seen`).
- Solo entrega/errores. Read-rate sin cambios.
- `build_data.py` arma `data.json` AL IMPORTARSE → NO se importa en tests; se verifica en localhost/cron.
- Reglas del hub: rama → **PR (no push directo a main)**; revisar en localhost primero; **no** regenerar `data.json` a mano para el commit (el cron lo reconstruye).

---

### Task 1: `sources_neon.delivery_by_msgid` + helper puro

**Files:**
- Modify: `marketing-loop/sources_neon.py`
- Test: `marketing-loop/tests/test_sources_neon.py` (crear si no existe)

**Interfaces:**
- Produces: `_delivery_dict(delivery_status, error_name, error_id) -> {"status","error_name"}` (puro); `delivery_by_msgid(country=None) -> {message_id: {"status","error_name"}}`.

- [ ] **Step 1: Escribir tests del helper puro (fallan)** — crear/append `marketing-loop/tests/test_sources_neon.py`:

```python
import sources_neon as N
import agg

def test_delivery_dict_with_error():
    d = N._delivery_dict("undeliverable", "EC_FREQUENCY_CAPPING", 7032)
    assert d["status"] == "undeliverable"
    assert d["error_name"] == "EC_FREQUENCY_CAPPING (code 7032)"
    assert agg.err_bucket(d["error_name"]) == "freq_cap"

def test_delivery_dict_no_error():
    d = N._delivery_dict("delivered", None, 0)
    assert d["status"] == "delivered" and d["error_name"] == "No Error (code 0)"
    assert agg.err_bucket(d["error_name"]) == "entregado"

def test_delivery_dict_invalido_code_351():
    d = N._delivery_dict("undeliverable", "EC_INVALID_DESTINATION", 351)
    assert agg.err_bucket(d["error_name"]) == "invalido"
```

- [ ] **Step 2: Verificar que fallan** — `cd marketing-loop && python3 -m pytest tests/test_sources_neon.py -q` → FAIL (`AttributeError: _delivery_dict`).

- [ ] **Step 3: Implementar en `sources_neon.py`** (agregar):

```python
def _delivery_dict(delivery_status, error_name, error_id):
    """Forma la entrada de mbm desde una fila de send_log. error_name con el formato
    '<NAME> (code <ID>)' que agg.err_bucket parsea (igual que mart/Infobip)."""
    if error_id in (None, 0):
        ename = "No Error (code 0)"
    else:
        ename = f"{error_name} (code {error_id})"
    return {"status": delivery_status, "error_name": ename}

def delivery_by_msgid(country=None):
    """Entrega persistida por el motor en send_log (durable, sin lag). {message_id: {status,error_name}}."""
    q = ("SELECT message_id, delivery_status, error_name, error_id FROM send_log "
         "WHERE message_id IS NOT NULL AND delivery_status IS NOT NULL")
    args = []
    if country:
        q += " AND country=%s"; args.append(country)
    return {r["message_id"]: _delivery_dict(r["delivery_status"], r["error_name"], r["error_id"])
            for r in _rows(q, tuple(args))}
```

- [ ] **Step 4: Verificar que pasan** — `python3 -m pytest tests/test_sources_neon.py -q` → PASS.

- [ ] **Step 5: Suite del tablero** — `python3 -m pytest tests/ -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add marketing-loop/sources_neon.py marketing-loop/tests/test_sources_neon.py
git commit -m "feat(sources_neon): delivery_by_msgid (entrega durable desde send_log) + helper puro"
```

---

### Task 2: `agg.merge_neon_delivery` (merge puro)

**Files:**
- Modify: `marketing-loop/agg.py`
- Test: `marketing-loop/tests/test_agg.py` (agregar)

**Interfaces:**
- Produces: `merge_neon_delivery(mbm, nbm) -> mbm` (muta e retorna `mbm`).

- [ ] **Step 1: Escribir tests (fallan)** — agregar a `marketing-loop/tests/test_agg.py`:

```python
def test_merge_neon_fills_missing():
    import agg
    mbm = {}
    agg.merge_neon_delivery(mbm, {"m1": {"status": "delivered", "error_name": "No Error (code 0)"}})
    assert mbm["m1"]["status"] == "delivered"

def test_merge_neon_terminal_overrides_pending():
    import agg
    mbm = {"m1": {"status": "pending", "error_name": "x", "seen": False}}
    agg.merge_neon_delivery(mbm, {"m1": {"status": "delivered", "error_name": "No Error (code 0)"}})
    assert mbm["m1"]["status"] == "delivered"

def test_merge_neon_does_not_regress_terminal_and_preserves_seen():
    import agg
    mbm = {"m1": {"status": "delivered", "error_name": "No Error (code 0)", "seen": True}}
    agg.merge_neon_delivery(mbm, {"m1": {"status": "pending", "error_name": "x"}})
    assert mbm["m1"]["status"] == "delivered" and mbm["m1"]["seen"] is True

def test_merge_neon_undeliverable_overrides_but_keeps_seen():
    import agg
    mbm = {"m1": {"status": "delivered", "error_name": "No Error (code 0)", "seen": True}}
    agg.merge_neon_delivery(mbm, {"m1": {"status": "undeliverable", "error_name": "EC_X (code 5)"}})
    assert mbm["m1"]["status"] == "undeliverable" and mbm["m1"]["seen"] is True
```

- [ ] **Step 2: Verificar que fallan** — `python3 -m pytest tests/test_agg.py -q` → FAIL (`AttributeError: merge_neon_delivery`).

- [ ] **Step 3: Implementar en `agg.py`** (agregar):

```python
_NEON_TERMINAL = {"delivered", "undeliverable", "rejected"}

def merge_neon_delivery(mbm, nbm):
    """Incorpora la entrega durable de Neon a mbm. Rellena lo ausente y pisa con estado terminal;
    nunca regresa un terminal a pending; preserva `seen` (Neon no lo trae)."""
    for mid, v in nbm.items():
        prev = mbm.get(mid)
        if prev is None or v.get("status") in _NEON_TERMINAL:
            mbm[mid] = {**(prev or {}), **v}
    return mbm
```

- [ ] **Step 4: Verificar que pasan** — `python3 -m pytest tests/test_agg.py -q` → PASS.

- [ ] **Step 5: Suite del tablero** — `python3 -m pytest tests/ -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add marketing-loop/agg.py marketing-loop/tests/test_agg.py
git commit -m "feat(agg): merge_neon_delivery — merge puro Neon->mbm (rellena/pisa terminal/preserva seen)"
```

---

### Task 3: Integración en `build_data.py`

**Files:**
- Modify: `marketing-loop/build_data.py`

**Interfaces:**
- Consumes: `N.delivery_by_msgid` (T1), `agg.merge_neon_delivery` (T2).

- [ ] **Step 1: Insertar el merge de Neon tras el de Infobip**

En `marketing-loop/build_data.py`, localizar el bloque del merge de Infobip (el `for mid, v in ibm.items(): ... mbm[mid] = {**v, "seen": ...}`). INMEDIATAMENTE DESPUÉS de ese `for`, agregar:

```python
    # Entrega DURABLE de Neon (persistida por el motor): rellena huecos del mart (p.ej. 22-jul) y pisa
    # con estado terminal, sin regresar terminales frescos ni tocar `seen`. Fuente propia, sin lag.
    nbm = N.delivery_by_msgid(country=pais)
    agg.merge_neon_delivery(mbm, nbm)
```

- [ ] **Step 2: Sumar el conteo al diagnóstico**

Localizar el dict de diagnóstico que incluye `"mart_msgids":len(mbm), "infobip":len(ibm)` y agregar `"neon_delivery": len(nbm),` en esa línea.

- [ ] **Step 3: Chequeo de sintaxis (no se puede importar: arma data.json al importar)**

Run: `cd marketing-loop && python3 -m py_compile build_data.py && echo OK`
Expected: `OK` (sin errores de sintaxis).

- [ ] **Step 4: Suite del tablero (build_data no se importa en tests)**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (sin regresión).

- [ ] **Step 5: Commit**

```bash
git add marketing-loop/build_data.py
git commit -m "feat(build_data): incorporar entrega de Neon a mbm (3a fuente durable) + diagnostico neon_delivery"
```

---

### Task 4: Revisión en localhost + PR + verificación (operación)

**Files:** ninguno.

- [ ] **Step 1: Build local con llaves (throwaway data.json, NO commitear)**

Run (con las llaves exportadas; NEON_DATABASE_URL + INFOBIP_MX/CO_API_KEY + GH_READ_TOKEN):
```bash
cd ~/habi/tableros-marketing/marketing-loop
NEON_DATABASE_URL=... INFOBIP_MX_API_KEY=... INFOBIP_CO_API_KEY=... GH_READ_TOKEN=$(gh auth token) python3 build_data.py
python3 -c "import json; d=json.load(open('data.json')); print('neon_delivery:', d['diagnostico'].get('neon_delivery')); [print(x['bucket'],'entr',x['entregados'],'resp',x['respondidos']) for x in d['cosecha']['MX']['dia'] if x['bucket']>='2026-07-23']"
```
Expected: `neon_delivery > 0`; días recientes con `entregados` consistente (sanity vs el conteo de `delivered` en Neon). El 22-jul seguirá en ~0 (data perdida — esperado).

- [ ] **Step 2: Revisar en localhost:8091**

```bash
cd ~/habi/tableros-marketing && python3 -m http.server 8091 &
```
Abrir `http://localhost:8091/marketing-loop/` → pestaña cosecha: la entrega de días recientes se ve; ningún cero falso nuevo. `git checkout -- marketing-loop/data.json` para descartar el data.json local (no se commitea).

- [ ] **Step 3: Push rama + PR (NO merge)**

```bash
cd ~/habi/tableros-marketing
git push -u origin feat/dashboard-delivery-neon
gh pr create --title "marketing-loop: entrega desde Neon (fuente durable, blinda huecos tipo 22-jul)" --body "<resumen + no revive 22-jul + read-rate intacto>"
```
Dejar SIN merge (Camilo revisa y mergea).

- [ ] **Step 4: (post-merge) Verificar el cron**

Tras el merge, el cron `update-marketing-loop.yml` reconstruye `data.json`. Verificar en el `data.json` de `origin/main`: `diagnostico.neon_delivery > 0` y cosecha reciente consistente.

---

## Notas de rollout
- El 22-jul NO se recupera (data perdida en todas las fuentes) — este cambio blinda hacia adelante.
- `data.json` lo reconstruye el cron; NO commitear el build local.
</content>
