import os, psycopg

# tz local por país para que el bucketeo por fecha sea hora local, no UTC.
TZ = {"MX": "America/Mexico_City", "CO": "America/Bogota"}

def _rows(sql, args=()):
    with psycopg.connect(os.environ["NEON_DATABASE_URL"]) as c:
        cur=c.execute(sql,args); cols=[d.name for d in cur.description]
        return [dict(zip(cols,r)) for r in cur.fetchall()]

def send_log_rows(days=None, country=None):
    # attempted_at convertido a tz local del país (country=None -> comportamiento actual: sin filtro, tz Mexico_City).
    tz = TZ.get(country, "America/Mexico_City")
    q=f"SELECT nid,deal_id,phone,line,template,message_id,api_http_code,accepted,(attempted_at AT TIME ZONE '{tz}')::text AS attempted_at FROM send_log"
    where=[]; args=[]
    if country: where.append("country=%s"); args.append(country)
    if days: where.append(f"attempted_at >= now() - make_interval(days => {int(days)})")
    if where: q += " WHERE " + " AND ".join(where)
    return _rows(q, tuple(args))

def recreation_rows(country=None):
    tz = TZ.get(country, "America/Mexico_City")
    q=f"SELECT old_nid,orig_deal_id,new_deal_id,new_nid,state_at_creation,http_code,success,responded_at::text,(created_at AT TIME ZONE '{tz}')::text AS created_at FROM recreation"
    args=[]
    if country: q += " WHERE country=%s"; args=[country]
    return _rows(q, tuple(args))

def contact_status_rows(country=None):
    q="SELECT phone,state,attempt_count,first_sent_at::text,last_sent_at::text,last_delivered_at::text,responded_at::text,reason FROM contact_status"
    args=[]
    if country: q += " WHERE country=%s"; args=[country]
    return _rows(q, tuple(args))
