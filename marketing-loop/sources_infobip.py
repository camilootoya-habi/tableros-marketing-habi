import os, requests

def map_log(x):
    st = (x.get("status") or {}).get("groupName","").lower()
    e = x.get("error") or {}
    eid = e.get("id")
    ename = f"{e.get('name')} (code {eid})" if eid else "No Error (code 0)"
    return {"status": st, "error_name": ename, "seen": False}

def delivery_by_msgid(msgids, pais="MX"):
    base = os.environ.get("INFOBIP_BASE_URL","https://xrwqpl.api.infobip.com")
    key = os.environ.get(f"INFOBIP_{pais}_API_KEY")
    if not key:
        print("WARN sources_infobip: falta INFOBIP_%s_API_KEY -> sin complemento tiempo real" % pais); return {}
    H={"Authorization":f"App {key}","Accept":"application/json"}
    ids=[m for m in dict.fromkeys(msgids) if m]
    out={}
    for i in range(0,len(ids),50):
        params=[("messageId",m) for m in ids[i:i+50]]
        try:
            r=requests.get(f"{base}/whatsapp/2/logs", headers=H, params=params, timeout=90)
            if r.status_code!=200:
                print(f"WARN sources_infobip http {r.status_code}: {r.text[:200]}"); continue
            for x in r.json().get("results",[]):
                mid=x.get("messageId")
                if mid: out[mid]=map_log(x)
        except Exception as ex:
            print("WARN sources_infobip batch:", ex)
    return out
