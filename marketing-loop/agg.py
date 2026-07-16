import re
import datetime

def bucket(dstr, tipo):
    try:
        y, m, d = map(int, dstr.split("-")[:3])
    except:
        return None
    dt = datetime.date(y, m, d)
    if tipo == "dia":
        return f"{y:04d}-{m:02d}-{d:02d}"
    if tipo == "mes":
        return f"{y:04d}-{m:02d}-01"
    if tipo == "semana":
        return (dt - datetime.timedelta(days=dt.weekday())).isoformat()
    if tipo == "ciclo":
        return (dt - datetime.timedelta(days=(dt.weekday() - 2) % 7)).isoformat()
    return None

_P = re.compile(r"activacion_NewLeads_(INTERESADO|YAVEND(?:I[ÓO]))_(\d+)", re.I)

def parse_resp(txt):
    if not txt:
        return {"action": "OTRO", "nid": None}
    m = _P.search(txt)
    if not m:
        return {"action": "OTRO", "nid": None}
    act = "INTERESADO" if m.group(1).upper() == "INTERESADO" else "YAVENDIO"
    return {"action": act, "nid": m.group(2)}

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
    ZERO = dict(intentos=0,aceptados=0,entregados=0,leidos=0,respondieron=0,
                interesados=0,recreados=0,calificados=0)
    serie = [{"fecha": d, **S.get(d, dict(ZERO))} for d in dias]   # rellena ceros en días sin actividad
    keys = ("intentos","aceptados","entregados","leidos","respondieron","interesados","recreados","calificados")
    tot = {k: sum(row[k] for row in serie) for k in keys}          # totales == Σ serie (acotado a dias)
    def rate(a,b): return round(a/b,3) if b else None
    return {"serie":serie,"totales":tot,"tasas":{
        "send_rate":rate(tot["aceptados"],tot["intentos"]),
        "delivery_rate":rate(tot["entregados"],tot["intentos"]),
        "read_rate":rate(tot["leidos"],tot["entregados"]),
        "respond_rate":rate(tot["respondieron"],tot["entregados"])}}

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
