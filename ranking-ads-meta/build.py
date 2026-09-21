#!/usr/bin/env python3
"""Ranking de ads de Meta: inversion, share del total y creativo.

Dos fuentes, y el reparto no es arbitrario:

  - BigQuery (`facebook_ads_data_global.ads_insights_region`) pone la plata y la
    entrega. Es la misma tabla de la que come el resto del hub, asi que los
    numeros cuadran con WBR y OKR en vez de contar una historia paralela.

  - La Marketing API pone la identidad y el creativo. No es capricho: esa tabla
    de BigQuery no trae `ad_name`, no trae `effective_status`, la tabla rica de
    CO (`facebook_ads_data_co.ads_insights`) esta muerta con 0 filas en 90 dias
    y `facebook_ads_data_co.ad_creatives` esta vacia. La imagen de un creativo
    no existe hoy en ningun lado de BigQuery.

Del entorno lee un solo secreto: META_PCOM_TOKEN (el System User
`AgenteMarketing`, que ya alcanza las dos cuentas de Habi). Corre en su propio
workflow, `update-ranking-ads.yml`.
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from PIL import Image

API = "https://graph.facebook.com/v21.0"

# IDs de cuenta: identificadores, no secretos. Mismo criterio que el PIXEL_ID
# hardcodeado en pauta-propiedades/src/pauta/meta_ads.py.
CUENTAS = {
    "770068953990542": "CO",   # Habi Colombia Sellers (USD)
    "205661715114408": "MX",   # Habi Mexico Sellers (USD)
}

VENTANAS = (7, 28, 90)
DIAS = max(VENTANAS)

# El facturador va fijo y NUNCA a un papyrus-*: esas credenciales perdieron
# bigquery.jobs.create y todo `bq query` vuelve Access Denied. Mismo criterio
# que scripts/run_queries.py.
BQ_PROJECT = "sellers-main-prod"
MAX_BYTES = 5_000_000_000  # el dry run de esta query da ~215 MB; el tope es holgura

THUMB_PX = 320      # lado mayor de la miniatura que se commitea
THUMB_Q = 60        # WebP q60 deja el creativo en ~10-15 KB
THUMB_PEDIDO = 400  # lo que se le pide a Meta; se baja localmente a THUMB_PX

AQUI = Path(__file__).resolve().parent
THUMBS = AQUI / "thumbs"

SQL = """
-- Inversion y entrega por ad y por dia, CO y MX en la misma tabla.
-- Las filas vienen abiertas por region: el SUM las vuelve a cerrar por ad x dia.
-- El dia en curso se excluye porque llega incompleto (Airbyte carga una vez al dia).
SELECT
  ad_id,
  account_id,
  CAST(date_start AS STRING) AS d,
  ROUND(SUM(spend), 4)       AS spend,
  SUM(impressions)           AS impr,
  SUM(clicks)                AS clicks
FROM `sellers-main-prod.facebook_ads_data_global.ads_insights_region`
WHERE date_start >= DATE_SUB(CURRENT_DATE(), INTERVAL {dias} DAY)
  AND date_start <  CURRENT_DATE()
  AND account_id IN ({cuentas})
GROUP BY ad_id, account_id, d
""".strip()


def log(msg):
    print(msg, flush=True)


# --------------------------------------------------------------- BigQuery ---

def correr_bq(sql):
    """`bq query` y devuelve la lista de filas. Igual que scripts/run_queries.py."""
    # En Windows `bq` es bq.cmd y subprocess no lo resuelve solo; en el runner
    # de Actions es un ejecutable normal.
    cmd = [
        shutil.which("bq") or "bq", "query", "--nouse_legacy_sql", "--format=json",
        f"--maximum_bytes_billed={MAX_BYTES}",
        "--max_rows=200000",
        f"--project_id={BQ_PROJECT}",
    ]
    r = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"bq fallo:\n{r.stderr.strip()[:2000]}")
    salida = r.stdout.strip()
    # bq imprime lineas de "Waiting on bqjob..." antes del JSON cuando la query tarda.
    corte = salida.find("[")
    return json.loads(salida[corte:]) if corte >= 0 else []


# -------------------------------------------------------------- Graph API ---

def graph(ruta, params, token, intentos=4):
    """GET a Graph con backoff. El codigo 17 es el rate limit de la app."""
    url = f"{API}/{ruta}" if ruta else f"{API}/"
    for intento in range(intentos):
        try:
            r = requests.get(url, params=params,
                             headers={"Authorization": f"Bearer {token}"}, timeout=90)
            cuerpo = r.json()
        except Exception:  # red, timeout, JSON roto
            if intento == intentos - 1:
                raise
            time.sleep(10 * (intento + 1))
            continue
        err = cuerpo.get("error") if isinstance(cuerpo, dict) else None
        if not err:
            return cuerpo
        if err.get("code") in (17, 613, 4, 32) and intento < intentos - 1:
            espera = 30 * (intento + 1)
            log(f"    rate limit (codigo {err['code']}), esperando {espera}s")
            time.sleep(espera)
            continue
        raise RuntimeError(f"Graph {err.get('code')}: {err.get('message', '')[:300]}")
    raise RuntimeError("Graph: se agotaron los intentos")


CAMPOS_AD = (
    "name,effective_status,"
    "campaign{name,objective},adset{name},"
    f"creative.thumbnail_width({THUMB_PEDIDO}).thumbnail_height({THUMB_PEDIDO})"
    "{id,thumbnail_url}"
)


def traer_ads(ids, token):
    """Metadata de los ads pedidos, en lotes de 50.

    Se piden por id y no barriendo /act_X/ads a proposito: solo interesan los
    que gastaron en la ventana, y una cuenta con anos de historia devuelve
    miles de ads muertos que nadie va a mirar.

    Si un id ya no es accesible (ad borrado), Graph tumba el lote entero; por
    eso el lote se parte en dos y se reintenta hasta aislar al culpable.
    """
    out = {}

    def lote(sub):
        if not sub:
            return
        try:
            out.update(graph("", {"ids": ",".join(sub), "fields": CAMPOS_AD}, token))
        except RuntimeError:
            if len(sub) == 1:
                log(f"    ad inaccesible, se muestra sin metadata: {sub[0]}")
                return
            mitad = len(sub) // 2
            lote(sub[:mitad])
            lote(sub[mitad:])

    for i in range(0, len(ids), 50):
        lote(ids[i:i + 50])
        log(f"  metadata {min(i + 50, len(ids))}/{len(ids)}")
    return out


def gasto_cuenta(act_id, desde, hasta, token):
    """Gasto total de la cuenta segun Meta, para cuadrar contra BigQuery.

    Las filas de ads_insights_region vienen abiertas por region y el gasto sin
    region atribuida podria no sumar al total. En vez de suponer que cuadra, se
    mide y el tablero lo ensena.
    """
    r = graph(f"act_{act_id}/insights", {
        "level": "account",
        "fields": "spend",
        "time_range": json.dumps({"since": desde, "until": hasta}),
    }, token)
    filas = r.get("data", [])
    return float(filas[0]["spend"]) if filas else 0.0


# -------------------------------------------------------------- Miniaturas ---

# creative_id -> archivo. Es el que evita volver a bajar lo ya bajado, y por eso
# se commitea junto a las imagenes.
INDICE = THUMBS / "index.json"


def cargar_indice():
    if INDICE.exists():
        return json.loads(INDICE.read_text(encoding="utf-8"))
    return {}


def miniatura(creative_id, url, indice):
    """Baja el creativo, lo reduce y lo deja en WebP. Devuelve el nombre.

    El archivo se nombra por el hash de la IMAGEN, no del creativo: medido sobre
    las 584 piezas vivas, 584 creativos distintos son solo 254 imagenes
    distintas —la misma pieza recreada una y otra vez—, asi que nombrar por
    creative_id guardaba el 59% de los bytes dos o mas veces.

    El indice creative_id -> archivo evita tener que bajar la imagen solo para
    descubrir que ya se tenia: el cron diario baja unicamente lo nuevo.
    """
    if not creative_id or not url:
        return None
    conocido = indice.get(creative_id)
    if conocido and (THUMBS / conocido).exists():
        return conocido
    try:
        datos = requests.get(url, timeout=60).content
        im = Image.open(io.BytesIO(datos)).convert("RGB")
        im.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=THUMB_Q, method=6)
        b = buf.getvalue()
        nombre = hashlib.sha1(b).hexdigest()[:16] + ".webp"
        destino = THUMBS / nombre
        if not destino.exists():
            destino.write_bytes(b)
        indice[creative_id] = nombre
        return nombre
    except Exception as e:
        log(f"    miniatura fallo para creative {creative_id}: {type(e).__name__}")
        return None


def podar(vivas, indice):
    """Borra las miniaturas y las entradas de indice que ya nadie referencia."""
    n = 0
    for f in THUMBS.glob("*.webp"):
        if f.name not in vivas:
            f.unlink()
            n += 1
    muertas = [c for c, a in indice.items() if a not in vivas]
    for c in muertas:
        del indice[c]
    INDICE.write_text(json.dumps(indice, separators=(",", ":"), sort_keys=True),
                      encoding="utf-8")
    if n:
        log(f"  podadas {n} miniaturas sin uso")


# -------------------------------------------------------------------- main ---

def main():
    token = os.environ.get("META_PCOM_TOKEN") or os.environ.get("META_SYSTEM_USER_TOKEN")
    if not token:
        sys.exit("Falta META_PCOM_TOKEN en el entorno.")

    THUMBS.mkdir(exist_ok=True)

    # 1. La plata, desde BigQuery.
    sql = SQL.format(dias=DIAS, cuentas=", ".join(f"'{c}'" for c in CUENTAS))
    log("Consultando BigQuery...")
    filas = correr_bq(sql)
    log(f"  {len(filas)} filas ad x dia")
    if not filas:
        sys.exit("BigQuery no devolvio filas: revisar la tabla antes de "
                 "escribir un data.json vacio.")

    dias_vistos = sorted({f["d"] for f in filas})
    hasta = dias_vistos[-1]

    # Acumulado por ad y por dia, y serie diaria por pais.
    por_ad = {}
    serie = {}
    for f in filas:
        pais = CUENTAS.get(f["account_id"])
        if not pais:
            continue
        d = f["d"]
        spend = float(f["spend"] or 0)

        a = por_ad.setdefault(f["ad_id"], {"p": pais, "dias": {}})
        acum = a["dias"].setdefault(d, [0.0, 0, 0])
        acum[0] += spend
        acum[1] += int(f["impr"] or 0)
        acum[2] += int(f["clicks"] or 0)

        serie.setdefault(d, {"CO": 0.0, "MX": 0.0})[pais] += spend

    # Cada ventana se corta por fecha, no por "ultimos N dias con datos": si una
    # cuenta no gasto un dia, ese dia igual cuenta como transcurrido.
    cortes = {}
    for v in VENTANAS:
        corte = (date.fromisoformat(hasta) - timedelta(days=v - 1)).isoformat()
        cortes[str(v)] = corte
        for a in por_ad.values():
            s = i = c = 0
            for d, (sp, im_, cl) in a["dias"].items():
                if d >= corte:
                    s += sp
                    i += im_
                    c += cl
            a.setdefault("w", {})[str(v)] = {"s": round(s, 2), "i": i, "c": c}

    # Solo los ads que movieron plata en la ventana larga. Un ad con 90 dias en
    # cero es ruido en un ranking de inversion.
    activos = [k for k, a in por_ad.items() if a["w"][str(DIAS)]["s"] > 0]
    log(f"  {len(activos)} ads con inversion en {DIAS} dias")

    # 2. La identidad y el creativo, desde la Marketing API.
    log("Consultando la Marketing API...")
    meta_ads = traer_ads(activos, token)

    log("Bajando miniaturas...")
    indice = cargar_indice()
    ads = []
    vivas = set()
    for ad_id in activos:
        a = por_ad[ad_id]
        m = meta_ads.get(ad_id, {})
        cre = m.get("creative") or {}
        th = miniatura(cre.get("id"), cre.get("thumbnail_url"), indice)
        if th:
            vivas.add(th)
        ads.append({
            "id": ad_id,
            "n": m.get("name") or "(sin nombre)",
            "p": a["p"],
            "st": m.get("effective_status") or "?",
            "cmp": (m.get("campaign") or {}).get("name") or "",
            "obj": (m.get("campaign") or {}).get("objective") or "",
            "ast": (m.get("adset") or {}).get("name") or "",
            "th": th,
            "w": a["w"],
        })
    podar(vivas, indice)

    # 3. El cuadre contra Meta.
    log("Cuadrando contra Meta...")
    cuadre = []
    for act, pais in CUENTAS.items():
        bq = round(sum(a["w"]["28"]["s"] for a in por_ad.values() if a["p"] == pais), 2)
        try:
            api = round(gasto_cuenta(act, cortes["28"], hasta, token), 2)
        except RuntimeError as e:
            log(f"  cuadre {pais} no disponible: {e}")
            api = None
        dif = round((bq - api) / api * 100, 2) if api else None
        cuadre.append({"p": pais, "bq": bq, "api": api, "dif_pct": dif})
        log(f"  {pais}: BigQuery {bq} vs Meta {api} ({dif}%)")

    salida = {
        "generado_en": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "desde": dias_vistos[0],
        "hasta": hasta,
        "cortes": cortes,
        "ventanas": list(VENTANAS),
        "cuadre": cuadre,
        "sql": sql,
        "serie": [{"d": d, **serie[d]} for d in dias_vistos],
        "ads": ads,
    }
    destino = AQUI / "data.json"
    destino.write_text(json.dumps(salida, separators=(",", ":"), ensure_ascii=False),
                       encoding="utf-8")
    log(f"OK: {len(ads)} ads -> {destino.name} "
        f"({destino.stat().st_size // 1024} KB), {len(vivas)} miniaturas")


if __name__ == "__main__":
    main()
