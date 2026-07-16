import os, psycopg
def _rows(sql, args=()):
    with psycopg.connect(os.environ["NEON_DATABASE_URL"]) as c:
        cur=c.execute(sql,args); cols=[d.name for d in cur.description]
        return [dict(zip(cols,r)) for r in cur.fetchall()]
def send_log_rows(days=None):
    # attempted_at en CDMX (America/Mexico_City) para que el bucketeo por fecha sea hora local, no UTC.
    q="SELECT nid,deal_id,phone,line,template,message_id,api_http_code,accepted,(attempted_at AT TIME ZONE 'America/Mexico_City')::text AS attempted_at FROM send_log"
    if days: q+=f" WHERE attempted_at >= now() - make_interval(days => {int(days)})"
    return _rows(q)
def recreation_rows():
    return _rows("SELECT old_nid,orig_deal_id,new_deal_id,new_nid,state_at_creation,http_code,success,responded_at::text,(created_at AT TIME ZONE 'America/Mexico_City')::text AS created_at FROM recreation")
def contact_status_rows():
    return _rows("SELECT phone,state,attempt_count,first_sent_at::text,last_sent_at::text,last_delivered_at::text,responded_at::text,reason FROM contact_status")
