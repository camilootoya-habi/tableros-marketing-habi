#!/usr/bin/env python3
"""Ensambla marketing-loop/data.json para el tablero Marketing Loop.
Fuentes: BigQuery (comparativa, funnel, creación, ciclo) + hojas públicas (respuestas, envíos base) + Infobip (calidad línea).
Uso: python3 build_data.py   (corre desde la carpeta del tablero; requiere bq autenticado).
Infobip opcional: env INFOBIP_BASE_URL + INFOBIP_MX_API_KEY + INFOBIP_CO_API_KEY."""
import json, os, csv, io, subprocess, datetime, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
def q(name):
    sql = open(os.path.join(HERE, name)).read()
    out = subprocess.run(["bq","query","--use_legacy_sql=false","--format=json","--max_rows=100000"],
        input=sql, capture_output=True, text=True, timeout=600)
    try: return json.loads(out.stdout)
    except Exception as e: print(f"WARN bq {name}: {e}\n{out.stdout[:300]}\n{out.stderr[:300]}"); return []

def sheet(url):
    raw = subprocess.run(["curl","-sL",url], capture_output=True, text=True, timeout=60).stdout
    return list(csv.DictReader(io.StringIO(raw)))

def n10(v):
    d = re.sub(r"[^0-9]","", v or ""); return d[-10:] if len(d)>=10 else None

# --- hojas ---
SS_RESP = "1gQGgBQHW5cUxMMc_N4IR6ylBkCmb-klITKbfL44AEsQ"
SS_ENV  = "1Jh7sIwv8Dkf-2VmW6wIfUSYexRmSu3iR_lZP7JUzD74"
RESP_GID = {"MX":"1470880789","CO":"158300647"}
ENV_GID  = {"MX":"241433433","CO":"1571565293"}
def csv_url(ss,gid): return f"https://docs.google.com/spreadsheets/d/{ss}/export?format=csv&gid={gid}"

def respuestas(pais):
    rows = sheet(csv_url(SS_RESP, RESP_GID[pais]))
    c = {"INTERESADO":0,"YA VENDIO":0,"PIDE BAJA":0}
    for r in rows:
        et = (r.get("ETAPA") or "").strip().upper()
        if et in c: c[et]+=1
    total = sum(c.values())
    return {"interesado":c["INTERESADO"], "ya_vendio":c["YA VENDIO"], "pide_baja":c["PIDE BAJA"], "total_respuestas":total}

def base_enviada(pais):
    # hoja de envíos: primeras filas metadata, luego teléfonos por columna
    raw = subprocess.run(["curl","-sL",csv_url(SS_ENV, ENV_GID[pais])], capture_output=True, text=True, timeout=60).stdout
    rows = list(csv.reader(io.StringIO(raw)))
    tel=set()
    for r in rows[2:]:
        for cell in r:
            t=n10(cell)
            if t: tel.add(t)
    return len(tel)

def linea(pais, sender):
    base=os.environ.get("INFOBIP_BASE_URL","https://xrwqpl.api.infobip.com")
    key=os.environ.get(f"INFOBIP_{pais}_API_KEY")
    if not key: return None
    try:
        out=subprocess.run(["curl","-s",f"{base}/whatsapp/2/senders?limit=200",
            "--header",f"Authorization: App {key}","--header","Accept: application/json"],
            capture_output=True,text=True,timeout=30).stdout
        d=json.loads(out); res=d.get("results") or d
        for s in res:
            if s.get("sender")==sender:
                return {"sender":sender,"quality":s.get("qualityRating"),"tier":s.get("limit"),"status":s.get("connectionStatus")}
    except Exception as e: print(f"WARN infobip {pais}: {e}")
    return None

def by_pais(rows, key="pais"):
    out={}
    for r in rows: out.setdefault(r.get(key), []).append(r)
    return out

data = {
  "updated": os.environ.get("BUILD_TS",""),
  "comparativa": q("query_comparativa.sql"),
  "funnel": q("query_funnel.sql"),
  "creacion": q("query_creacion.sql"),
  "ciclo": q("query_ciclo.sql"),
  "respuestas": {p: respuestas(p) for p in ("MX","CO")},
  "base_enviada": {p: base_enviada(p) for p in ("MX","CO")},
  "linea": {"MX": linea("MX","5215590883423"), "CO": linea("CO","573009110453")},
}
open(os.path.join(HERE,"data.json"),"w").write(json.dumps(data, ensure_ascii=False, separators=(",",":")))
print("data.json OK |",
      "comparativa",len(data["comparativa"]),
      "| funnel",len(data["funnel"]),
      "| creacion",len(data["creacion"]),
      "| ciclo",len(data["ciclo"]),
      "| resp MX",data["respuestas"]["MX"], "| base MX",data["base_enviada"]["MX"],
      "| linea MX",data["linea"]["MX"])
