# Renovación tablero Marketing Loop MX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-cablear el tablero `marketing-loop/` a Neon + mart + Meta (fuentes del proyecto nuevo), eliminar lo obsoleto (Sheets, ledgers CSV, geo/address health), y agregar indicadores de entrega/errores.

**Architecture:** `build_data.py` se reestructura en 4 lectores (Neon vía psycopg, mart vía bq, Meta Graph, BQ tig/hubspot). La llave de join es `send_log.message_id ⋈ mart.message_id`. El frontend (`index.html`) consume `data.json` con las keys nuevas y arranca la granularidad en "día". MX-first.

**Tech Stack:** Python 3.11 (`psycopg[binary]`, `bq` CLI vía subprocess, `requests`/curl), BigQuery, Neon Postgres, Meta Graph API, HTML/JS estático (patrón del hub).

## Global Constraints

- **MX-first.** CO queda "pendiente" (sin mart CO); no se invierte en CO.
- **Granularidad default = "día"** en todos los selectores.
- **Ventana embudo = 7 días completos** (excluye hoy).
- **Llave de join:** `send_log.message_id ⋈ mart.message_id`.
- **Líneas MX:** activa `5215595483481` + vieja `5215590883423` (histórico). Mart: `papyrus-master.infobib_gold_mx.mart_infobip_messages_daily_mx`.
- **Neon:** 3 tablas `send_log` (nid, deal_id, phone, line, template, message_id, api_http_code, accepted, attempted_at), `recreation` (old_nid, orig_deal_id, new_deal_id, new_nid, state_at_creation, http_code, success, responded_at, created_at), `contact_status` (phone, state, attempt_count, first_sent_at, last_sent_at, last_delivered_at, responded_at, reason). Secret nuevo `NEON_DATABASE_URL` en el cron del hub.
- **Estados backbone:** calificado = `id_last_state` ∈ {20, 63} (MM); Duplicado = 1.
- **Errores Infobip (error_name → bucket):** code 0=entregado · 7032=freq-cap · 7020=device-error · 351=inválido · 7009=template · 566=bloqueado-operador · resto=otro.
- **Regla del hub:** trabajar en rama `renovacion-marketing-loop-mx`, revisar en **localhost** antes de PR, **NO push a main** (Camilo mergea). NUNCA editar el `index.html` de la raíz (generado).
- Parse de respuestas del mart: regex `activacion_NewLeads_(INTERESADO|YAVEND(?:I[ÓO]))_(\d+)` sobre `respuesta_cliente`; sin match = texto libre.

---

## File Structure

```
marketing-loop/
  build_data.py          # reestructurado: 4 lectores + ensamblado data.json
  sources_neon.py        # NUEVO: lectura de Neon (send_log/recreation/contact_status)
  sources_mart.py        # NUEVO: lectura del mart (outbound/inbound/errores) por líneas
  agg.py                 # NUEVO: funciones PURAS de agregación (bucketing, embudo, errores, cohorte, dedup) — TDD
  index.html             # renders nuevos/re-trabajados + default día + quitar secciones muertas
  query_completitud.sql  # se mantiene
  query_hoy.sql / query_creacion.sql (asignados) # se mantienen los que sigan válidos
  tests/test_agg.py      # NUEVO: tests de agg.py
  (ELIMINAR: query_comparativa.sql, query_ciclo.sql)
.github/workflows/update-marketing-loop.yml  # agregar env NEON_DATABASE_URL + pip psycopg
```

Decisión de decomposición: `agg.py` (puro, testeable) separa la lógica de agregación de los lectores I/O (`sources_neon.py`, `sources_mart.py`), para poder testear el cálculo de tasas/buckets sin tocar DB.

---

## Phase 0 — Setup

### Task 1: Rama, dependencia y secret del cron

**Files:**
- Modify: `.github/workflows/update-marketing-loop.yml`

**Interfaces:**
- Produces: entorno del cron con `NEON_DATABASE_URL` disponible y `psycopg` instalado.

- [ ] **Step 1: Confirmar rama**

Run: `cd ~/habi/tableros-marketing && git branch --show-current`
Expected: `renovacion-marketing-loop-mx`

- [ ] **Step 2: Agregar psycopg + secret al workflow**

En `.github/workflows/update-marketing-loop.yml`, en el step que corre `build_data.py`: (a) asegurar `pip install psycopg[binary]` junto a las deps existentes; (b) pasar el env `NEON_DATABASE_URL: ${{ secrets.NEON_DATABASE_URL }}` al step. Mostrar el bloque exacto tras editar:
```yaml
      - name: build marketing-loop data
        env:
          NEON_DATABASE_URL: ${{ secrets.NEON_DATABASE_URL }}
          META_ACCESS_TOKEN: ${{ secrets.META_ACCESS_TOKEN }}
          # (mantener INFOBIP_*/GH_READ_TOKEN existentes)
        run: |
          pip install "psycopg[binary]"
          cd marketing-loop && python3 build_data.py
```

- [ ] **Step 3: Acción manual de Camilo (documentar, no ejecutable)**

Agregar el secret `NEON_DATABASE_URL` en Settings→Secrets del repo `tableros-marketing-habi` (read-only role de Neon idealmente). El plan PAUSA aquí para que Camilo lo cree antes de que el cron real corra; local usa `.env`/export.

- [ ] **Step 4: Commit**
```bash
git add .github/workflows/update-marketing-loop.yml
git commit -m "chore(marketing-loop): psycopg + NEON_DATABASE_URL en el cron"
```

---

## Phase 1 — Agregación pura (TDD)

> `agg.py`: funciones puras que reciben listas de dicts (filas ya leídas) y devuelven las estructuras de `data.json`. Sin I/O. Es el corazón lógico.

### Task 2: Bucketing + parse de payload

**Files:**
- Create: `marketing-loop/agg.py`, `marketing-loop/tests/test_agg.py`

**Interfaces:**
- Produces:
  - `bucket(dstr, tipo)` → string del bucket (dia=YYYY-MM-DD, semana=lunes, mes=YYYY-MM-01, ciclo=miércoles). Igual semántica que el `bucket()` actual de build_data.
  - `parse_resp(respuesta_cliente)` → `{"action":"INTERESADO"|"YAVENDIO"|"OTRO","nid":str|None}`.

- [ ] **Step 1: Test que falla**
```python
# marketing-loop/tests/test_agg.py
from agg import bucket, parse_resp
def test_bucket_dia(): assert bucket("2026-07-15","dia")=="2026-07-15"
def test_bucket_mes(): assert bucket("2026-07-15","mes")=="2026-07-01"
def test_bucket_semana(): assert bucket("2026-07-15","semana")=="2026-07-13"  # lunes
def test_parse_interesado():
    r=parse_resp("BUTTON - Text: Estoy interesado, Payload: activacion_NewLeads_INTERESADO_123")
    assert r=={"action":"INTERESADO","nid":"123"}
def test_parse_baja():
    r=parse_resp("BUTTON - Text: Darme de baja, Payload: activacion_NewLeads_YAVENDIÓ_9")
    assert r["action"]=="YAVENDIO" and r["nid"]=="9"
def test_parse_libre():
    assert parse_resp("Hola quiero info")=={"action":"OTRO","nid":None}
```

- [ ] **Step 2: Run → FAIL** — `cd marketing-loop && python3 -m pytest tests/test_agg.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Implementar en `agg.py`**
```python
import re, datetime
def bucket(dstr, tipo):
    try: y,m,d = map(int, dstr.split("-")[:3])
    except: return None
    dt=datetime.date(y,m,d)
    if tipo=="dia": return f"{y:04d}-{m:02d}-{d:02d}"
    if tipo=="mes": return f"{y:04d}-{m:02d}-01"
    if tipo=="semana": return (dt-datetime.timedelta(days=dt.weekday())).isoformat()
    if tipo=="ciclo":  return (dt-datetime.timedelta(days=(dt.weekday()-2)%7)).isoformat()
    return None
_P = re.compile(r"activacion_NewLeads_(INTERESADO|YAVEND(?:I[ÓO]))_(\d+)", re.I)
def parse_resp(txt):
    if not txt: return {"action":"OTRO","nid":None}
    m=_P.search(txt)
    if not m: return {"action":"OTRO","nid":None}
    act="INTERESADO" if m.group(1).upper()=="INTERESADO" else "YAVENDIO"
    return {"action":act,"nid":m.group(2)}
```

- [ ] **Step 4: Run → PASS** (5 passed)
- [ ] **Step 5: Commit** — `git add marketing-loop/agg.py marketing-loop/tests/test_agg.py && git commit -m "feat(agg): bucket + parse_resp con tests"`

### Task 3: Embudo de salida + tasas (agg puro)

**Files:**
- Modify: `marketing-loop/agg.py`, `marketing-loop/tests/test_agg.py`

**Interfaces:**
- Consumes: filas de send_log (dict con `message_id`,`accepted`,`phone`,`attempted_at`,`nid`), mapa `mart_by_msgid` (`{message_id:{"status":str,"error_name":str,"seen":bool}}`), set `inbound_phones`, set `interesado_phones`, recreation rows.
- Produces: `embudo(sendlog, mart_by_msgid, inbound_phones, interesado_phones, recreated_oldnids, qualified_oldnids, dias)` → `{"serie":[{fecha,intentos,aceptados,entregados,leidos,respondieron,interesados,recreados,calificados}], "totales":{...}, "tasas":{send_rate,delivery_rate,read_rate,respond_rate}}`.

- [ ] **Step 1: Test que falla**
```python
from agg import embudo
def test_embudo_tasas():
    sl=[{"message_id":"a","accepted":True,"phone":"1","attempted_at":"2026-07-10","nid":"n1"},
        {"message_id":"b","accepted":True,"phone":"2","attempted_at":"2026-07-10","nid":"n2"},
        {"message_id":None,"accepted":False,"phone":"3","attempted_at":"2026-07-10","nid":"n3"}]
    mart={"a":{"status":"delivered","error_name":"No Error (code 0)","seen":True},
          "b":{"status":"undeliverable","error_name":"Frequency capping limit reached (code 7032)","seen":False}}
    r=embudo(sl, mart, inbound_phones={"1"}, interesado_phones={"1"},
             recreated_oldnids={"n1"}, qualified_oldnids={"n1"}, dias=["2026-07-10"])
    t=r["totales"]
    assert t["intentos"]==3 and t["aceptados"]==2 and t["entregados"]==1 and t["leidos"]==1
    assert t["respondieron"]==1 and t["interesados"]==1 and t["recreados"]==1 and t["calificados"]==1
    assert round(r["tasas"]["delivery_rate"],2)==0.33 and round(r["tasas"]["respond_rate"],2)==1.0
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implementar `embudo` en `agg.py`**
```python
def embudo(sendlog, mart_by_msgid, inbound_phones, interesado_phones,
           recreated_oldnids, qualified_oldnids, dias):
    from collections import defaultdict
    S=defaultdict(lambda: dict(intentos=0,aceptados=0,entregados=0,leidos=0,
                               respondieron=0,interesados=0,recreados=0,calificados=0))
    for r in sendlog:
        d=(r.get("attempted_at") or "")[:10]
        s=S[d]; s["intentos"]+=1
        if r.get("accepted"): s["aceptados"]+=1
        m=mart_by_msgid.get(r.get("message_id") or "")
        if m and m.get("status")=="delivered":
            s["entregados"]+=1
            if m.get("seen"): s["leidos"]+=1
        if r.get("phone") in inbound_phones: s["respondieron"]+=1
        if r.get("phone") in interesado_phones: s["interesados"]+=1
        if r.get("nid") in recreated_oldnids: s["recreados"]+=1
        if r.get("nid") in qualified_oldnids: s["calificados"]+=1
    serie=[{"fecha":d, **S[d]} for d in dias if d in S]
    tot={k:sum(S[d][k] for d in S) for k in
         ("intentos","aceptados","entregados","leidos","respondieron","interesados","recreados","calificados")}
    def rate(a,b): return round(a/b,3) if b else None
    return {"serie":serie,"totales":tot,"tasas":{
        "send_rate":rate(tot["aceptados"],tot["intentos"]),
        "delivery_rate":rate(tot["entregados"],tot["intentos"]),
        "read_rate":rate(tot["leidos"],tot["entregados"]),
        "respond_rate":rate(tot["respondieron"],tot["entregados"])}}
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git commit -am "feat(agg): embudo de salida con tasas"`

### Task 4: Errores por tipo + cohorte por antigüedad (agg puro)

**Files:**
- Modify: `marketing-loop/agg.py`, `marketing-loop/tests/test_agg.py`

**Interfaces:**
- Produces:
  - `err_bucket(error_name)` → `"entregado"|"freq_cap"|"device_error"|"invalido"|"template"|"bloqueado"|"otro"`.
  - `errores_por_tipo(sendlog, mart_by_msgid)` → `{bucket:count,...,"total":n}`.
  - `cohorte(sendlog, mart_by_msgid, nid2quarter)` → `[{"bucket":"YYYY-QN","enviados":n,"entregados":n,"freq_cap":n,"device_error":n}]` ordenado.

- [ ] **Step 1: Test que falla**
```python
from agg import err_bucket, errores_por_tipo, cohorte
def test_err_bucket():
    assert err_bucket("Frequency capping limit reached (code 7032)")=="freq_cap"
    assert err_bucket("User device was not able to reproduce the content (code 7020)")=="device_error"
    assert err_bucket("No Error (code 0)")=="entregado"
def test_cohorte():
    sl=[{"message_id":"a","nid":"n1"},{"message_id":"b","nid":"n2"}]
    mart={"a":{"error_name":"No Error (code 0)"},"b":{"error_name":"...(code 7020)"}}
    q={"n1":"2024-Q1","n2":"2024-Q1"}
    r=cohorte(sl,mart,q)
    assert r[0]["bucket"]=="2024-Q1" and r[0]["enviados"]==2 and r[0]["device_error"]==1 and r[0]["entregados"]==1
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implementar en `agg.py`**
```python
def err_bucket(en):
    en=(en or "").lower()
    if "code 0" in en or "no error" in en: return "entregado"
    if "7032" in en: return "freq_cap"
    if "7020" in en: return "device_error"
    if "351" in en: return "invalido"
    if "7009" in en: return "template"
    if "566" in en: return "bloqueado"
    return "otro"
def errores_por_tipo(sendlog, mart_by_msgid):
    from collections import Counter
    c=Counter()
    for r in sendlog:
        m=mart_by_msgid.get(r.get("message_id") or "")
        c[err_bucket(m.get("error_name") if m else None)]+=1
    d=dict(c); d["total"]=sum(c.values()); return d
def cohorte(sendlog, mart_by_msgid, nid2quarter):
    from collections import defaultdict
    A=defaultdict(lambda: dict(enviados=0,entregados=0,freq_cap=0,device_error=0))
    for r in sendlog:
        q=nid2quarter.get(r.get("nid"))
        if not q: continue
        a=A[q]; a["enviados"]+=1
        m=mart_by_msgid.get(r.get("message_id") or "")
        b=err_bucket(m.get("error_name") if m else None)
        if b=="entregado": a["entregados"]+=1
        elif b=="freq_cap": a["freq_cap"]+=1
        elif b=="device_error": a["device_error"]+=1
    return [{"bucket":k, **A[k]} for k in sorted(A)]
```

- [ ] **Step 4: Run → PASS** · **Step 5: Commit** — `git commit -am "feat(agg): errores por tipo + cohorte por antiguedad"`

### Task 5: Recreación + dedup outcome + contact_status (agg puro)

**Files:**
- Modify: `marketing-loop/agg.py`, `marketing-loop/tests/test_agg.py`

**Interfaces:**
- Produces:
  - `recreacion_serie(recreation_rows, tipo)` → `[{"bucket","recreados","duplicado","calificado"}]` (por `created_at`, `state_at_creation`: 1=dup, 20=calif).
  - `antifunnel_serie(recreation_rows, tipo)` → `[{"bucket","estados":{estado_actual:count}}]` (usa `estado_actual` que el lector adjunta).
  - `contact_dist(contact_rows)` → `{state:count,...}`.

- [ ] **Step 1: Test que falla**
```python
from agg import recreacion_serie, contact_dist
def test_recreacion():
    rr=[{"created_at":"2026-07-14","state_at_creation":1},{"created_at":"2026-07-14","state_at_creation":20}]
    r=recreacion_serie(rr,"dia")
    assert r[0]=={"bucket":"2026-07-14","recreados":2,"duplicado":1,"calificado":1}
def test_contact_dist():
    assert contact_dist([{"state":"enviado"},{"state":"baja"},{"state":"enviado"}])=={"enviado":2,"baja":1}
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implementar en `agg.py`**
```python
def recreacion_serie(recreation_rows, tipo):
    from collections import defaultdict
    A=defaultdict(lambda: dict(recreados=0,duplicado=0,calificado=0))
    for r in recreation_rows:
        b=bucket((r.get("created_at") or "")[:10], tipo)
        if not b: continue
        a=A[b]; a["recreados"]+=1
        st=r.get("state_at_creation")
        if st==1: a["duplicado"]+=1
        elif st==20: a["calificado"]+=1
    return [{"bucket":k, **A[k]} for k in sorted(A)]
def antifunnel_serie(recreation_rows, tipo):
    from collections import defaultdict
    A=defaultdict(dict)
    for r in recreation_rows:
        b=bucket((r.get("created_at") or "")[:10], tipo)
        if not b: continue
        lab=str(r.get("estado_actual") if r.get("estado_actual") is not None else "sin estado")
        A[b][lab]=A[b].get(lab,0)+1
    return [{"bucket":k,"estados":A[k]} for k in sorted(A)]
def contact_dist(contact_rows):
    from collections import Counter
    return dict(Counter(r.get("state") for r in contact_rows if r.get("state")))
```

- [ ] **Step 4: Run → PASS** · **Step 5: Commit** — `git commit -am "feat(agg): recreacion/dedup/antifunnel/contact_status"`

---

## Phase 2 — Lectores I/O

### Task 6: `sources_neon.py`

**Files:**
- Create: `marketing-loop/sources_neon.py`

**Interfaces:**
- Produces: `send_log_rows(days=None)`, `recreation_rows()`, `contact_status_rows()` → cada uno `list[dict]` con las columnas de la tabla. Conexión vía `os.environ["NEON_DATABASE_URL"]`. `attempted_at`/`created_at` como string ISO (`[:10]` usable).

- [ ] **Step 1: Escribir `sources_neon.py`**
```python
import os, psycopg
def _rows(sql, args=()):
    with psycopg.connect(os.environ["NEON_DATABASE_URL"]) as c:
        cur=c.execute(sql,args); cols=[d.name for d in cur.description]
        return [dict(zip(cols,r)) for r in cur.fetchall()]
def send_log_rows(days=None):
    q="SELECT nid,deal_id,phone,line,template,message_id,api_http_code,accepted,attempted_at::text FROM send_log"
    if days: q+=f" WHERE attempted_at >= now() - make_interval(days => {int(days)})"
    return _rows(q)
def recreation_rows():
    return _rows("SELECT old_nid,orig_deal_id,new_deal_id,new_nid,state_at_creation,http_code,success,responded_at::text,created_at::text FROM recreation")
def contact_status_rows():
    return _rows("SELECT phone,state,attempt_count,first_sent_at::text,last_sent_at::text,last_delivered_at::text,responded_at::text,reason FROM contact_status")
```

- [ ] **Step 2: Smoke test (real Neon)** — `cd marketing-loop && python3 -c "import sources_neon as s; print('send_log',len(s.send_log_rows()),'| recreation',len(s.recreation_rows()),'| contact',len(s.contact_status_rows()))"` → conteos > 0 (recreation ~848, contact ~17k+).
- [ ] **Step 3: Commit** — `git add marketing-loop/sources_neon.py && git commit -m "feat: lector Neon del tablero"`

### Task 7: `sources_mart.py`

**Files:**
- Create: `marketing-loop/sources_mart.py`

**Interfaces:**
- Produces:
  - `mart_by_msgid(days=30)` → `{message_id:{"status":str,"error_name":str,"seen":bool}}` de outbound de nuestras líneas.
  - `inbound_rows(days=30)` → `[{"phone":str10,"ts":str,"respuesta_cliente":str}]`.
  - `nid2quarter(nids)` → `{nid:"YYYY-QN"}` desde tig por fecha_creacion.
  - `estado_actual_by_deal(deal_ids)` → `{deal_id:id_last_state}` desde tig.

- [ ] **Step 1: Escribir `sources_mart.py`** (bq vía subprocess, filtrado a líneas MX; reusar patrón `bq_sql` existente de build_data)
```python
import subprocess, json, re
MART="papyrus-master.infobib_gold_mx.mart_infobip_messages_daily_mx"
TIG="papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general"
LINES=["5215595483481","5215590883423"]
SENDAT='SAFE.PARSE_DATETIME("%d/%m/%Y %H:%M:%S", TRIM(send_at_raw))'
def _bq(sql):
    out=subprocess.run(["bq","query","--use_legacy_sql=false","--format=json","--max_rows=200000"],
        input=sql,capture_output=True,text=True,timeout=600)
    try: return json.loads(out.stdout)
    except Exception as e: print("WARN bq",e); return []
def _d10(v): d=re.sub(r"[^0-9]","",v or ""); return d[-10:] if len(d)>=10 else None
def mart_by_msgid(days=30):
    lines=",".join(f'"{l}"' for l in LINES)
    rows=_bq(f'''SELECT message_id, LOWER(TRIM(status)) status, error_name,
        (TRIM(seen_at) NOT IN ("","-") AND seen_at IS NOT NULL) seen
      FROM `{MART}` WHERE service_name="WhatsApp Outbound" AND TRIM(from_number) IN ({lines})
        AND DATE({SENDAT}) >= DATE_SUB(CURRENT_DATE(), INTERVAL {int(days)} DAY)''')
    return {r["message_id"]:{"status":r["status"],"error_name":r.get("error_name"),
            "seen":str(r.get("seen")).lower()=="true"} for r in rows if r.get("message_id")}
def inbound_rows(days=30):
    lines=",".join(f'"{l}"' for l in LINES)
    rows=_bq(f'''SELECT from_number, respuesta_cliente, {SENDAT} ts
      FROM `{MART}` WHERE service_name="WhatsApp Inbound" AND TRIM(to_number) IN ({lines})
        AND DATE({SENDAT}) >= DATE_SUB(CURRENT_DATE(), INTERVAL {int(days)} DAY)''')
    return [{"phone":_d10(r.get("from_number")),"ts":(r.get("ts") or "")[:10],
             "respuesta_cliente":r.get("respuesta_cliente")} for r in rows]
def nid2quarter(nids):
    if not nids: return {}
    inl=",".join(f"'{n}'" for n in nids if str(n).isdigit())
    if not inl: return {}
    rows=_bq(f"SELECT CAST(nid AS STRING) nid, EXTRACT(YEAR FROM fecha_creacion) y, EXTRACT(QUARTER FROM fecha_creacion) q FROM `{TIG}` WHERE CAST(nid AS STRING) IN ({inl})")
    return {r["nid"]:f"{r['y']}-Q{r['q']}" for r in rows if r.get("y")}
def estado_actual_by_deal(deal_ids):
    ids=[str(d) for d in deal_ids if d]
    if not ids: return {}
    inl=",".join(f"'{d}'" for d in ids)
    rows=_bq(f"SELECT CAST(id_negocio AS STRING) deal, id_last_state st FROM `{TIG}` WHERE CAST(id_negocio AS STRING) IN ({inl})")
    return {r["deal"]:r.get("st") for r in rows}
```

- [ ] **Step 2: Smoke test** — `python3 -c "import sources_mart as m; d=m.mart_by_msgid(7); print('mart msgids',len(d)); print('inbound',len(m.inbound_rows(7)))"` → conteos > 0.
- [ ] **Step 3: Commit** — `git add marketing-loop/sources_mart.py && git commit -m "feat: lector mart del tablero"`

---

## Phase 3 — Ensamblado build_data.py

### Task 8: Reescribir `build_data.py` con los lectores nuevos

**Files:**
- Modify: `marketing-loop/build_data.py`

**Interfaces:**
- Consumes: `agg`, `sources_neon`, `sources_mart`, `linea_meta` (se conserva), queries BQ que se mantienen (completitud, asignados, hoy).
- Produces: `data.json` con keys: `updated, linea, embudo, errores, respuestas, cohorte, ab_templates, recreacion, antifunnel, contact_status, por_hora, completitud, asignados, hoy` (MX). CO: keys presentes pero `null`/`"pendiente"`.

- [ ] **Step 1: Reescribir el ensamblado** (mantener `linea_meta`, `por_hora`, `read_stats`, `completitud`, asignados; eliminar `resp_rows`/`base_enviada`/`fetch_private_csv`/geo/address/comparativa/ciclo). Ensamblar con los lectores nuevos. Código del bloque `data = {...}`:
```python
import agg, sources_neon as N, sources_mart as M, datetime
WIN=7
sl = N.send_log_rows()                        # todos (para cohorte histórica)
sl7 = [r for r in sl if r["attempted_at"][:10] >= (datetime.date.today()-datetime.timedelta(days=WIN)).isoformat()
       and r["attempt ed_at"[:0]+"attempted_at"][:10] < datetime.date.today().isoformat()]  # 7d completos
rec = N.recreation_rows(); cst = N.contact_status_rows()
mbm = M.mart_by_msgid(30)
inb = M.inbound_rows(30)
# respuestas parseadas del mart
parsed=[(i["phone"], agg.parse_resp(i["respuesta_cliente"]), i["ts"]) for i in inb]
inbound_phones={p for p,_,_ in parsed if p}
interesado_phones={p for p,pr,_ in parsed if p and pr["action"]=="INTERESADO"}
# recreados/calificados por old_nid
recreated_oldnids={r["old_nid"] for r in rec if r.get("success")}
qualified_oldnids={r["old_nid"] for r in rec if r.get("state_at_creation") in (20,63)}
dias=[(datetime.date.today()-datetime.timedelta(days=k)).isoformat() for k in range(WIN,0,-1)]
# cohorte necesita nid->trimestre
nidq=M.nid2quarter(list({r["nid"] for r in sl if r.get("nid")}))
# antifunnel: estado actual de recreados
est=M.estado_actual_by_deal([r["new_deal_id"] for r in rec if r.get("new_deal_id")])
for r in rec: r["estado_actual"]=est.get(str(r.get("new_deal_id")))
data={
  "updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
  "linea": {"MX": linea_meta("MX"), "CO": None},
  "embudo": {"MX": agg.embudo(sl7,mbm,inbound_phones,interesado_phones,recreated_oldnids,qualified_oldnids,dias), "CO": None},
  "errores": {"MX": agg.errores_por_tipo(sl7,mbm), "CO": None},
  "respuestas": {"MX": _resp_tipos(parsed, mbm, WIN), "CO": None},
  "cohorte": {"MX": agg.cohorte(sl,mbm,nidq), "CO": None},
  "ab_templates": {"MX": _ab(sl,mbm,inbound_phones), "CO": None},
  "recreacion": {"MX": {t: agg.recreacion_serie(rec,t) for t in ("dia","semana","mes")}, "CO": None},
  "antifunnel": {"MX": {t: agg.antifunnel_serie(rec,t) for t in ("dia","semana","mes")}, "CO": None},
  "contact_status": {"MX": agg.contact_dist(cst), "CO": None},
  "por_hora": {"MX": por_hora("MX"), "CO": {"serie":[]}},
  "completitud": {p: completitud(p, COMP) for p in ("MX","CO")},
  "hoy": {r["pais"]: int(r.get("creados_hoy") or 0) for r in q("query_hoy.sql")},
}
```
Definir helpers `_resp_tipos(parsed, mbm, win)` (cuenta INTERESADO/YAVENDIO/OTRO en la ventana + respond_rate=respuestas/entregados) y `_ab(sl,mbm,inbound_phones)` (por `template`: enviados, delivery%, respond_rate) en el mismo archivo. (Nota: corregir el typo ilustrativo de `sl7` a un filtro limpio por fecha en la implementación real.)

- [ ] **Step 2: Correr build local** — con `NEON_DATABASE_URL` + bq + `META_ACCESS_TOKEN` exportados: `cd marketing-loop && python3 build_data.py` → escribe `data.json` sin error; imprime conteos.
- [ ] **Step 3: Validar keys y cifras** — `python3 -c "import json;d=json.load(open('marketing-loop/data.json'));print(list(d));print('embudo tasas',d['embudo']['MX']['tasas']);print('errores',d['errores']['MX'])"` → `delivery_rate` ~0.44, freq_cap ~36% de intentos, device_error ~19% (cuadra con lo medido hoy).
- [ ] **Step 4: Commit** — `git commit -am "feat(build_data): re-cableo a Neon+mart; elimina Sheets/ledgers/geo/address/comparativa/ciclo"`

### Task 9: Eliminar queries y código muerto

**Files:**
- Delete: `marketing-loop/query_comparativa.sql`, `marketing-loop/query_ciclo.sql`
- Modify: `marketing-loop/build_data.py` (quitar imports/funcs residuales), `marketing-loop/build_audit.py` si referencia lo eliminado.

- [ ] **Step 1: Verificar qué renderizan antes de borrar** — `grep -n "comparativa\|ciclo\|geo_health\|address_health" marketing-loop/*.py marketing-loop/index.html` → confirmar que solo alimentan secciones que se eliminan.
- [ ] **Step 2: Borrar y limpiar** — `git rm marketing-loop/query_comparativa.sql marketing-loop/query_ciclo.sql`; quitar funciones `sheet/resp_rows/base_enviada/fetch_private_csv/fetch_private_json/diario/funnel_tables/antifunnel(viejo)/cohorte_origen(viejo)` y sus llamadas.
- [ ] **Step 3: Re-correr build** — `python3 build_data.py` → sigue OK.
- [ ] **Step 4: Commit** — `git commit -am "chore(build_data): elimina lectores Sheets/ledgers y queries comparativa/ciclo"`

---

## Phase 4 — Frontend (`index.html`)

> Seguir el patrón existente (funciones `render*`, selector `#granSel`, consumo de `D`/data.json). Validar en localhost (`python3 -m http.server` en la carpeta del tablero).

### Task 10: Default granularidad día + quitar secciones muertas

**Files:**
- Modify: `marketing-loop/index.html`

- [ ] **Step 1: Default día** — en `index.html:178`, mover `selected` de `semana` a `dia`:
```html
<select class="sel" id="granSel"><option value="dia" selected>Diario</option><option value="ciclo">Ciclo comercial (Mié→Mar)</option><option value="semana">Semana (Lun→Dom)</option><option value="mes">Mes</option></select>
```
- [ ] **Step 2: Quitar renders muertos** — eliminar las funciones y sus llamadas: `renderGeoAlarm`, `renderComparativa`, `renderCiclo`, y los contenedores HTML de esas secciones (geo alarm, comparativa, ciclo). Quitar cualquier referencia a `D.geo_health/D.address_health/D.comparativa/D.ciclo`.
- [ ] **Step 3: Verificar en localhost** — servir la carpeta y confirmar que la página carga sin errores JS (consola limpia) y sin las secciones eliminadas.
- [ ] **Step 4: Commit** — `git commit -am "feat(index): default granularidad dia + quita geo/comparativa/ciclo"`

### Task 11: Re-trabajar renders existentes a las keys nuevas

**Files:**
- Modify: `marketing-loop/index.html`

- [ ] **Step 1: `renderSalida` → embudo nuevo** — leer `D.embudo.MX` (`serie`+`totales`+`tasas`); render del embudo con las 8 etapas y las 4 tasas. Respetar el selector de granularidad para la serie (si aplica) o mostrar totales de la ventana 7d.
- [ ] **Step 2: `renderResp` → `D.respuestas.MX`** (mart): INTERESADO/ya vendió/baja/texto libre + respond_rate.
- [ ] **Step 3: `renderCohorteOrigen` → `D.cohorte.MX`**: tabla por trimestre con columnas enviados · delivery% · freq-cap% · device-error%.
- [ ] **Step 4: `renderFuntab`/`renderAntifunnel` → `D.recreacion.MX`/`D.antifunnel.MX`** (Neon): usar la granularidad del selector (default día).
- [ ] **Step 5: Verificar en localhost** cada sección con datos reales.
- [ ] **Step 6: Commit** — `git commit -am "feat(index): renders re-cableados a embudo/respuestas/cohorte/recreacion del nuevo data.json"`

### Task 12: Renders nuevos (errores, A/B, contact_status, dedup outcome)

**Files:**
- Modify: `marketing-loop/index.html`

- [ ] **Step 1: `renderErrores`** — card/tabla de `D.errores.MX` (buckets + % sobre intentos). Barra apilada o tabla.
- [ ] **Step 2: `renderAB`** — `D.ab_templates.MX`: por template enviados/delivery%/respond_rate; nota "comparativa se activa con ≥2 templates".
- [ ] **Step 3: `renderContacto`** — `D.contact_status.MX`: distribución por estado (dona/barras).
- [ ] **Step 4: `renderDedup`** — de `D.recreacion.MX`: % Duplicado vs calificado (el outcome de dedup).
- [ ] **Step 5: Registrar las nuevas en el init** (donde se llaman los `render*` tras `fetch('data.json')`), y agregar sus contenedores HTML.
- [ ] **Step 6: Verificar en localhost** — todas las secciones nuevas renderizan con datos reales.
- [ ] **Step 7: Commit** — `git commit -am "feat(index): renders nuevos errores/AB/contact_status/dedup outcome"`

---

## Phase 5 — Validación y cierre

### Task 13: Validación end-to-end + textos de referencia

**Files:**
- Modify: `marketing-loop/index.html` (textos: Definición de la base → piso 2023 + fuentes 3/47), `marketing-loop/meta.json` (si cambia descripción)

- [ ] **Step 1: Actualizar "Definición de la base"** en el HTML: creación **2023-01-01→hoy−180d**, fuentes **3 (WEB)+47 (Lead Forms)**, calificado por backbone (20/36/63 · 20/36/73 inmo), con dirección, descarte duro, dedup en cadena.
- [ ] **Step 2: Cotejo de cifras** — comparar el embudo/errores del tablero con lo medido hoy vía API de logs (entrega ~44%, freq-cap ~36%, device ~19%). Documentar el cotejo en el reporte.
- [ ] **Step 3: Revisión localhost completa** — servir y revisar todas las secciones; consola sin errores; granularidad arranca en día.
- [ ] **Step 4: Commit** — `git commit -am "feat(index): definicion de base actualizada (2023, fuentes 3/47)"`

### Task 14: PR (NO merge)

- [ ] **Step 1: Push de la rama** — `git push -u origin renovacion-marketing-loop-mx`
- [ ] **Step 2: Abrir PR** con `gh pr create` describiendo la renovación (Neon+mart, indicadores nuevos, kills). **NO mergear** — Camilo revisa y mergea (regla del hub). El cron reconstruye `data.json` tras el merge (con el secret ya cargado).

---

## Self-Review

**1. Spec coverage:** §4.1 línea→Task 8(linea_meta) ✓ · §4.2 embudo→T3/T8/T11 ✓ · §4.3 errores→T4/T8/T12 ✓ · §4.4 por_hora→T8(se mantiene) ✓ · §4.5 respuestas mart→T2/T8/T11 ✓ · §4.6 A/B→T8/T12 ✓ · §4.7 cohorte→T4/T8/T11 ✓ · §4.8 recreación+dedup→T5/T8/T12 ✓ · §4.9 antifunnel→T5/T8/T11 ✓ · §4.10 contact_status→T5/T8/T12 ✓ · §4.11 mantener (completitud/asignados/definición/plantillas)→T8/T13 ✓ · §4.12 eliminar→T9/T10 ✓ · §5 frontend default día→T10 ✓ · §6 secret/psycopg→T1 ✓.
**Gap identificado y aceptado:** "Plantillas dinámico desde Infobip" (§4.11) es menor; queda como mejora dentro de T13 si hay tiempo (hoy la sección de plantillas puede seguir estática con v1+v2 listadas a mano). Lo anoto, no bloquea.
**2. Placeholder scan:** el bloque de `data=` en Task 8 tiene un typo ILUSTRATIVO en el filtro `sl7` — marcado explícitamente para corregir en implementación (filtro limpio por fecha 7d completos). Los helpers `_resp_tipos`/`_ab` se especifican por interfaz (contrato claro) para implementar en Task 8. No hay TBD.
**3. Type consistency:** `mart_by_msgid` (dict message_id→{status,error_name,seen}) usado consistente en embudo/errores/cohorte. `parse_resp`/`err_bucket`/`bucket` firmas estables. recreation `state_at_creation` int (1/20) consistente en agg y build_data.
