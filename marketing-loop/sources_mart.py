import subprocess, json, re

MART = {
    "MX": "papyrus-master.infobib_gold_mx.mart_infobip_messages_daily_mx",
    "CO": "papyrus-master.infobib_gold_co.mart_infobip_messages_daily_co",
}
TIG = {
    "MX": "papyrus-data-mx.habi_wh_bi.tabla_inmuebles_general",
    "CO": "papyrus-data.habi_wh_bi.tabla_inmuebles_general",
}
LINES = {
    "MX": ["5215595483481","5215590883423"],
    "CO": ["573009110453"],
}
# la tabla TIG usa nombres de columna distintos para deal/estado según país (mismo propósito, distinto esquema físico)
TIG_DEAL_COL  = {"MX": "id_negocio",    "CO": "negocio_id"}
TIG_STATE_COL = {"MX": "id_last_state", "CO": "last_estado_id"}

SENDAT='SAFE.PARSE_DATETIME("%d/%m/%Y %H:%M:%S", TRIM(send_at_raw))'

def _bq(sql):
    out=subprocess.run(["bq","query","--use_legacy_sql=false","--format=json","--max_rows=200000"],
        input=sql,capture_output=True,text=True,timeout=600)
    try: return json.loads(out.stdout)
    except Exception as e: print("WARN bq",e); return []

def _d10(v): d=re.sub(r"[^0-9]","",v or ""); return d[-10:] if len(d)>=10 else None

def mart_by_msgid(days=30, country="MX"):
    lines=",".join(f'"{l}"' for l in LINES[country])
    rows=_bq(f'''SELECT message_id, LOWER(TRIM(status)) status, error_name,
        (TRIM(seen_at) NOT IN ("","-") AND seen_at IS NOT NULL) seen
      FROM `{MART[country]}` WHERE service_name="WhatsApp Outbound" AND TRIM(from_number) IN ({lines})
        AND DATE({SENDAT}) >= DATE_SUB(CURRENT_DATE(), INTERVAL {int(days)} DAY)''')
    return {r["message_id"]:{"status":r["status"],"error_name":r.get("error_name"),
            "seen":str(r.get("seen")).lower()=="true"} for r in rows if r.get("message_id")}

def inbound_rows(days=30, country="MX"):
    lines=",".join(f'"{l}"' for l in LINES[country])
    rows=_bq(f'''SELECT from_number, respuesta_cliente, {SENDAT} ts
      FROM `{MART[country]}` WHERE service_name="WhatsApp Inbound" AND TRIM(to_number) IN ({lines})
        AND DATE({SENDAT}) >= DATE_SUB(CURRENT_DATE(), INTERVAL {int(days)} DAY)''')
    return [{"phone":_d10(r.get("from_number")),"ts":(r.get("ts") or "")[:10],
             "respuesta_cliente":r.get("respuesta_cliente")} for r in rows]

def nid2quarter(nids, country="MX"):
    if not nids: return {}
    inl=",".join(f"'{n}'" for n in nids if str(n).isdigit())
    if not inl: return {}
    rows=_bq(f"SELECT CAST(nid AS STRING) nid, EXTRACT(YEAR FROM fecha_creacion) y, EXTRACT(QUARTER FROM fecha_creacion) q FROM `{TIG[country]}` WHERE CAST(nid AS STRING) IN ({inl})")
    return {r["nid"]:f"{r['y']}-Q{r['q']}" for r in rows if r.get("y")}

def estado_actual_by_deal(deal_ids, country="MX"):
    ids=[str(d) for d in deal_ids if str(d).isdigit()]
    if not ids: return {}
    inl=",".join(f"'{d}'" for d in ids)
    deal_col, state_col = TIG_DEAL_COL[country], TIG_STATE_COL[country]
    rows=_bq(f"SELECT CAST({deal_col} AS STRING) deal, {state_col} st FROM `{TIG[country]}` WHERE CAST({deal_col} AS STRING) IN ({inl})")
    return {r["deal"]:r.get("st") for r in rows}
