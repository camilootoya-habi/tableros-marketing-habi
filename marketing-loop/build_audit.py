#!/usr/bin/env python3
"""Genera marketing-loop/audit.json para el EXPLORADOR de la base (hojas 3 y 4 del tablero).
Para cada propiedad-filtro: todos los valores en la ventana (2023→180d) con conteo 'en ventana'
(universo) vs 'en base' (los que pasan TODA la cadena de filtros ROW-LEVEL del query vigente).
Sirve para auditar qué entra/queda excluido. Conteos a nivel fila (pre-dedup y pre-guard a nivel
persona, con fanout del join a deals). Fuente/piso alineados con outbound_{co,mx}.sql del motor.
Uso: python3 build_audit.py  (requiere bq autenticado). Cron aparte (diario), NO el de 10 min."""
import json, os, csv, io, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = {
  "CO": dict(proj="papyrus-data",
             nijoin='`sellers-main-prod.co_rds_staging.habi_db_tabla_negocio_inmueble` ni ON ni.id=g.negocio_id',
             mm="ni.last_estado_id", inmo="ni.last_state_id_real_estate", country="Colombia",
             direc='dir_h!=""', fuente="3,47,7,20",
             live='"Sellers - Market Maker CO (NUEVO)","Nuevo - Inmobiliaria CO"'),
  "MX": dict(proj="papyrus-data-mx",
             nijoin='`sellers-main-prod.mx_rds_staging.habi_db_property_deal` ni ON ni.id=g.id_negocio',
             mm="ni.last_state_id", inmo="ni.last_state_id_real_estate", country="México",
             direc='dir_h!=""', fuente="3,47",
             live='"Sellers - Market Maker MX (NUEVO)","Nuevo - Inmobiliaria MX"'),
}
HARD = ('"Ya vendió","Ya vendio","Rechazo definitivo de comité",'
        '"Rechazo oferta no volver a llamar","Duplicado","Datos de contacto incorrectos"')

def sql(c):
    x = CFG[c]
    tig = f"`{x['proj']}.habi_wh_bi.tabla_inmuebles_general`"
    return f'''
WITH L AS (
  SELECT g.fuente_id, {x['mm']} mm_state, {x['inmo']} inmo_state,
    hd.oportunidad_del_negocio opn, hd.oportunidad_inmobiliaria opi,
    COALESCE(NULLIF(TRIM(p.label),""),"(sin pipeline)") pipe, s.label etapa,
    hd.estado_comite_remodelaciones remo, hd.razon_rechazo_remodelaciones remo_razon,
    hd.razon_de_descartado d, hd.razon_de_descarte_mm mm, hd.razon_de_descarte_inmo inmo,
    RIGHT(REGEXP_REPLACE(g.telefono,r"[^0-9]",""),10) ph10,
    {("TRIM(COALESCE(g.direccion,'')) dir_g," if c=="CO" else "'' dir_g,")} TRIM(COALESCE(hd.direccion,"")) dir_h
  FROM {tig} g
  LEFT JOIN {x['nijoin']}
  LEFT JOIN `sellers-main-prod.hubspot.deals` hd ON hd.nid=g.nid AND hd.country="{x['country']}"
  LEFT JOIN `sellers-main-prod.hubspot.deal_pipelines_stages` s ON s.id=hd.dealstage
  LEFT JOIN `sellers-main-prod.hubspot.deal_pipelines` p ON p.id=s.pipeline_id
  WHERE CAST(g.fecha_creacion AS DATE) >= "2023-01-01"
    AND CAST(g.fecha_creacion AS DATE) < DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
),
B AS (SELECT *, (
    (COALESCE(mm_state,-1) IN (20,36,63) OR COALESCE(inmo_state,-1) IN (20,36,73))
    AND fuente_id IN ({x['fuente']})
    AND COALESCE(opn,"") NOT IN ("Cierre - Comprado","Vendido Sales","Descartado","Descartado por comité","descartado por dirección","Rechazó oferta - No volver a llamar")
    AND COALESCE(opi,"") NOT IN ("Contrato firmado","Oferta aceptada","Pendiente Envio Legal","Enviado a Legal","Ya vendio","Descartado por Comite","Aprobación comité final","Precio Aprobado")
    AND (COALESCE(pipe,"") NOT IN ({x['live']}) OR TRIM(etapa)="Perdido")
    AND COALESCE(remo,"")!="REJECTED"
    AND COALESCE(TRIM(remo_razon),"") NOT IN ("Ampliaciones ilegales","Grietas, fallas estructurales","Humedad Grave","Rechazado, documentos","Rechazado, Mayor 40 años","Servicios públicos","Rechazado, parqueadero en servidumbre","Filtraciones parqueadero y/o deposito")
    AND REGEXP_CONTAINS(ph10,r"^[0-9]{{10}}$") AND ph10 != REPEAT(SUBSTR(ph10,1,1),10)
    AND ({x['direc']})
    AND NULLIF(TRIM(d),"") IS NULL
    AND COALESCE(TRIM(mm),"") NOT IN ({HARD})
    AND COALESCE(TRIM(inmo),"") NOT IN ({HARD})
  ) in_base FROM L)
SELECT y.campo, y.valor, COUNT(*) ventana, COUNTIF(in_base) base
FROM B, UNNEST([
  STRUCT("00.pipeline" AS campo, pipe AS valor),
  ("01.estado_MM", CAST(mm_state AS STRING)),
  ("02.estado_Inmo", CAST(inmo_state AS STRING)),
  ("03.oport_MM", COALESCE(NULLIF(TRIM(opn),""),"(vacío)")),
  ("04.oport_Inmo", COALESCE(NULLIF(TRIM(opi),""),"(vacío)")),
  ("05.etapa", COALESCE(NULLIF(TRIM(etapa),""),"(vacío)")),
  ("06.comite_remo", COALESCE(NULLIF(TRIM(remo),""),"(vacío)")),
  ("07.remo_razon", COALESCE(NULLIF(TRIM(remo_razon),""),"(vacío)")),
  ("08.descartado", COALESCE(NULLIF(TRIM(d),""),"(vacío)")),
  ("09.descarte_MM", COALESCE(NULLIF(TRIM(mm),""),"(vacío)")),
  ("10.descarte_Inmo", COALESCE(NULLIF(TRIM(inmo),""),"(vacío)"))
]) y
GROUP BY 1,2 ORDER BY 1, ventana DESC
'''

def run(c):
    out = subprocess.run(["bq","query","--project_id="+CFG[c]["proj"],"--use_legacy_sql=false",
        "--format=csv","--max_rows=100000"], input=sql(c), capture_output=True, text=True, timeout=600)
    rows = {}
    for r in csv.reader(io.StringIO(out.stdout)):
        if len(r)<4 or r[0]=="campo": continue
        try: rows.setdefault(r[0],[]).append({"valor":r[1],"ventana":int(r[2]),"base":int(r[3])})
        except: pass
    if not rows: print(f"WARN {c}: sin filas\n{out.stdout[:300]}\n{out.stderr[:300]}")
    return rows

data = {"updated": os.environ.get("BUILD_TS") or datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
        "CO": run("CO"), "MX": run("MX")}
open(os.path.join(HERE,"audit.json"),"w").write(json.dumps(data, ensure_ascii=False, separators=(",",":")))
print("audit.json OK | CO props", len(data["CO"]), "| MX props", len(data["MX"]))
