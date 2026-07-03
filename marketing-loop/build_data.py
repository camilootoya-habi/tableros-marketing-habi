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

# --- serie diaria: envíos (repo privado) + respuestas/interesados (hoja) ---
GH_TOKEN = os.environ.get("GH_READ_TOKEN")
PRIV_REPO = "camilootoya-habi/marketing-loop-lead-nurturing"
SENT_PATH = {"MX":"backbone-mx-batch/infobip_sent_history_mx.csv","CO":"backbone-mx-batch/infobip_sent_history_co.csv"}
def fetch_private_csv(path):
    if not GH_TOKEN: print("  ⚠ sin GH_READ_TOKEN, no leo envíos privados"); return []
    out=subprocess.run(["curl","-s","-H",f"Authorization: token {GH_TOKEN}","-H","Accept: application/vnd.github.raw",
        f"https://api.github.com/repos/{PRIV_REPO}/contents/{path}"],capture_output=True,text=True,timeout=60).stdout
    return list(csv.DictReader(io.StringIO(out)))
def norm_date(s):
    s=(s or "").strip()
    m=re.match(r"(\d{4})-(\d{2})-(\d{2})",s)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m=re.match(r"(\d{2})-(\d{2})-(\d{4})",s)   # DD-MM-YYYY
    if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None
def diario(pais, crea=None):
    env={}
    for r in fetch_private_csv(SENT_PATH[pais]):
        if "hatsapp" in (r.get("canal") or "").lower():
            d=norm_date(r.get("fecha_envio"))
            if d: env[d]=env.get(d,0)+1
    resp={}; inter={}; yv={}; pb={}
    for r in sheet(csv_url(SS_RESP, RESP_GID[pais])):
        d=None
        for k,v in r.items():
            if k and "Fecha" in k and v: d=norm_date(v); break
        if not d: continue
        resp[d]=resp.get(d,0)+1
        et=(r.get("ETAPA") or "").upper()
        if "INTERESADO" in et: inter[d]=inter.get(d,0)+1
        elif "YA VENDIO" in et: yv[d]=yv.get(d,0)+1
        elif "PIDE BAJA" in et: pb[d]=pb.get(d,0)+1
    cre={}; cal={}
    for r in (crea or []):
        if r.get("pais")==pais:
            d=norm_date(r.get("fecha"))
            if d: cre[d]=int(r.get("creados") or 0); cal[d]=int(r.get("calificados") or 0)
    dias=sorted(set(env)|set(resp)|set(inter)|set(cre))
    return [{"fecha":d,"enviados":env.get(d,0),"respuestas":resp.get(d,0),"interesados":inter.get(d,0),
             "ya_vendio":yv.get(d,0),"pide_baja":pb.get(d,0),
             "creados":cre.get(d,0),"calificados":cal.get(d,0)} for d in dias]

def respuestas(pais):
    rows = sheet(csv_url(SS_RESP, RESP_GID[pais]))
    hoy = datetime.date.today()
    ini = hoy - datetime.timedelta(days=14)   # ventana: últimos 14 días completos, sin incluir hoy: [hoy-14, hoy-1]
    def fdate(r):
        for k,v in r.items():
            if k and "Fecha" in k and v:
                m = re.search(r"(\d{4})-(\d{2})-(\d{2})", v)
                if m:
                    try: return datetime.date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
                    except: return None
        return None
    c = {"INTERESADO":0,"YA VENDIO":0,"PIDE BAJA":0}
    for r in rows:
        d = fdate(r)
        if not d or d < ini or d >= hoy: continue   # excluye hoy y >14 días
        et = (r.get("ETAPA") or "").strip().upper()
        if et in c: c[et]+=1
    total = sum(c.values())
    return {"interesado":c["INTERESADO"], "ya_vendio":c["YA VENDIO"], "pide_baja":c["PIDE BAJA"], "total_respuestas":total, "ventana":"14d"}

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

# --- funnel por cosecha (atribuido al último envío) / por fecha de evento ---
LEDGER_PATHS = {
  "MX": ["backbone-mx-batch/decoy_mx_ledger.csv","backbone-mx-batch/backbone-leads-mx-ledger.csv","backbone-mx-batch/mapping_confianza.csv"],
  "CO": ["backbone-mx-batch/backbone-leads-co-ledger.csv","backbone-mx-batch/decoy_co_ledger.csv"],
}
def bucket(dstr, tipo):
    try: y,m,dd = map(int, dstr.split("-"))
    except: return None
    dt=datetime.date(y,m,dd)
    if tipo=="dia": return dstr
    if tipo=="mes": return f"{y:04d}-{m:02d}-01"
    if tipo=="semana": return (dt-datetime.timedelta(days=dt.weekday())).isoformat()          # lunes
    if tipo=="ciclo":  return (dt-datetime.timedelta(days=(dt.weekday()-2)%7)).isoformat()     # miércoles
def funnel_tables(pais, recre):
    sends={}
    for r in fetch_private_csv(SENT_PATH[pais]):
        if "hatsapp" not in (r.get("canal") or "").lower(): continue
        d=norm_date(r.get("fecha_envio")); ph=r.get("telefono_10")
        if d and ph: sends.setdefault(ph,[]).append(d)
    for ph in sends: sends[ph].sort()
    def last_send(ph,before):
        L=sends.get(ph);  prev=[x for x in (L or []) if x<=before]
        return prev[-1] if prev else (L[0] if L else None)
    # respuestas: (telefono, nid_original, fecha, etapa)
    resp=[]
    for r in sheet(csv_url(SS_RESP, RESP_GID[pais])):
        d=None
        for k,v in r.items():
            if k and "Fecha" in k and v: d=norm_date(v); break
        ph=n10(r.get("Telefono")); nid=(r.get("NID") or "").strip()
        if d and ph: resp.append((ph,nid,d,(r.get("ETAPA") or "").upper()))
    # info del lead recreado, indexada por nid nuevo y por deal_id (=id_negocio). El deal_id cubre los decoy (sin new_nid).
    info_nid={}; info_deal={}
    for r in recre:
        if r.get("pais")!=pais: continue
        rec=(r.get("fecha_creacion"), int(r.get("calif") or 0))
        if r.get("nid"): info_nid[str(r["nid"])]=rec
        if r.get("deal_id"): info_deal[str(r["deal_id"])]=rec
    # ledger: old_nid -> (fecha_recreacion, calificó). Enlaza por new_nid o, si es decoy (sin nid), por deal_id.
    old2rec={}
    for path in LEDGER_PATHS[pais]:
        for r in fetch_private_csv(path):
            on=(r.get("old_nid") or "").strip()
            if not on: continue
            nn=(r.get("new_nid") or r.get("decoy_nid") or "").strip()
            did=(r.get("new_deal_id") or r.get("decoy_deal_id") or "").strip()
            info=info_nid.get(nn) or info_deal.get(did)
            ts=(r.get("timestamp") or "")[:10]
            fecha=(info[0] if info else None) or (ts or None)
            calif=info[1] if info else 0
            old2rec[on]=(fecha,calif)
    out={"cosecha":{},"evento":{}}
    for tipo in ("dia","ciclo","semana","mes"):
        C={}; E={}
        def add(D,b,k):
            if not b: return
            D.setdefault(b,{"enviados":0,"respondieron":0,"interesados":0,"creados":0,"calificados":0})[k]+=1
        for ph,dates in sends.items():
            for d in dates:
                b=bucket(d,tipo); add(E,b,"enviados"); add(C,b,"enviados")
        # creados/calificados se anclan al INTERESADO (recreamos el 100%): creados = interesados recreados.
        # cosecha → cohorte del envío que originó la respuesta; evento → fecha real de recreación.
        for ph,nid,d,et in resp:
            be=bucket(d,tipo); cs=last_send(ph,d); bc=bucket(cs,tipo) if cs else None
            add(E,be,"respondieron"); add(C,bc,"respondieron")
            if "INTERESADO" not in et: continue
            add(E,be,"interesados"); add(C,bc,"interesados")
            rec=old2rec.get(nid)
            if not rec: continue
            fecha,cal=rec
            add(C,bc,"creados")
            if cal: add(C,bc,"calificados")
            add(E,bucket(fecha,tipo),"creados")
            if cal: add(E,bucket(fecha,tipo),"calificados")
        out["cosecha"][tipo]=[{"bucket":b,**v} for b,v in sorted(C.items())]
        out["evento"][tipo]=[{"bucket":b,**v} for b,v in sorted(E.items())]
    return out

CREA = q("query_creacion.sql")
RECRE = q("query_recreados.sql")
data = {
  "updated": os.environ.get("BUILD_TS",""),
  "comparativa": q("query_comparativa.sql"),
  "funnel": q("query_funnel.sql"),
  "creacion": CREA,
  "ciclo": q("query_ciclo.sql"),
  "respuestas": {p: respuestas(p) for p in ("MX","CO")},
  "base_enviada": {p: base_enviada(p) for p in ("MX","CO")},
  "diario": {p: diario(p, CREA) for p in ("MX","CO")},
  "funnel_tabla": {p: funnel_tables(p, RECRE) for p in ("MX","CO")},
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
