#!/usr/bin/env python3
"""Guardia de estado del listing — SOLO APAGA, jamás prende.

Corre en GitHub Actions (cron). Pausa en Meta los ads ACTIVE cuyo listing en
Propiedades.com ya no está activo (Eliminado / Vencido / Vendida / …), según la
card pública de Metabase. Nunca activa ni crea nada.

Conservador a propósito (bot desatendido): solo pausa cuando Metabase tiene la
propiedad con un estatus explícito NO-activo. Las 'Sin dato' (ausentes de
Metabase) NO se tocan — se revisan a mano vía la alarma del tablero.

Env: META_PCOM_TOKEN, META_PCOM_AD_ACCOUNT.  GUARDIA_DRY_RUN=1 = no escribe.
"""
import json
import os

import requests

import ledger

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOGO = os.path.join(HERE, "catalogo.json")

API_VERSION = "v21.0"
BASE = f"https://graph.facebook.com/{API_VERSION}"
TOKEN = os.environ.get("META_PCOM_TOKEN", "")
AD_ACCOUNT = os.environ.get("META_PCOM_AD_ACCOUNT", "")
DRY_RUN = os.environ.get("GUARDIA_DRY_RUN", "") in ("1", "true", "True")

METABASE_CARD = "51604d7d-00ed-46af-8223-78a0a01b940d"
METABASE_URL = f"https://metabase.propiedades.com/api/public/card/{METABASE_CARD}/query/json"

# El listing está "vivo" para pautar solo en estos estatus.
OK_STATUSES = {"Activo", "Destacado"}


def _check(resp):
    data = resp.json()
    if resp.status_code >= 400 or "error" in data:
        err = data.get("error", data)
        raise RuntimeError(f"{err.get('code')} {err.get('message')}".strip())
    return data


def listing_status():
    data = requests.get(METABASE_URL, timeout=60).json()
    return {str(r["Property_id"]): (r.get("Estatus") or "Sin dato")
            for r in data if r.get("Property_id") is not None}


def ad_status_map():
    """ad_id -> effective_status (para saber cuáles están entregando)."""
    url = f"{BASE}/{AD_ACCOUNT}/ads"
    params = {"fields": "id,effective_status", "limit": 500, "access_token": TOKEN}
    out = {}
    while url:
        data = _check(requests.get(url, params=params, timeout=90))
        for r in data.get("data", []):
            out[r["id"]] = r.get("effective_status", "")
        url = data.get("paging", {}).get("next")
        params = None
    return out


def pause(ad_id):
    return _check(requests.post(f"{BASE}/{ad_id}",
                                data={"status": "PAUSED", "access_token": TOKEN}))


def main():
    pubs = json.load(open(CATALOGO, encoding="utf-8"))["publicaciones"]
    status = listing_status()
    ads = ad_status_map()

    objetivo = []
    for p in pubs:
        est = status.get(str(p["id_aviso"]))
        # solo estatus explícito NO-activo (ignora ausentes / 'Sin dato')
        if est is None or est in OK_STATUSES:
            continue
        if ads.get(p["ad_id"]) == "ACTIVE":
            objetivo.append((p["ad_id"], p["id_aviso"], est, p.get("cliente_id")))

    print(f"Guardia de estado{' (DRY RUN)' if DRY_RUN else ''}: "
          f"{len(objetivo)} ads ACTIVE sobre listings no-activos.")
    ok = 0
    for ad_id, id_aviso, est, cliente_id in objetivo:
        if DRY_RUN:
            print(f"  [dry] pausaría {ad_id}  {est:10s} {id_aviso}")
            continue
        try:
            pause(ad_id)
            ok += 1
            try:
                ledger.log_event("PAUSED", cliente_id, ad_id=ad_id,
                                 id_aviso=str(id_aviso), razon=est,
                                 fuente="guardia",
                                 detalle={"estatus_listing": est, "actor": "guardia"})
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠ ledger no registró la pausa de {ad_id}: {e}")
            print(f"  ✓ PAUSED {ad_id}  {est:10s} {id_aviso}")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ ERROR  {ad_id}  {id_aviso}: {e}")
    if not DRY_RUN:
        print(f"Pausados: {ok}/{len(objetivo)}.")


if __name__ == "__main__":
    main()
