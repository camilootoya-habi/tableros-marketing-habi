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
