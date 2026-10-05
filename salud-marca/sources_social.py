"""Seguidores de Facebook e Instagram de las tres marcas.

Lo que da Meta (verificado el 5-oct-2026 con el token del system user AgenteCreativo):
- **Facebook**: total de seguidores por día (`page_follows`), altas (`page_daily_follows_unique`)
  y bajas (`page_daily_unfollows_unique`). Hay al menos 2 años de historia, en ventanas de 90 días.
- **Instagram**: el total de HOY (`followers_count`) y los seguidores nuevos por día
  (`follower_count`), solo de los últimos 30 días. No da bajas ni el total de días pasados.

Por eso el caché versionado (`social_cache.json`) es la fuente de verdad: el total de Instagram
existe solo desde el día en que se empezó a guardar la foto diaria, y los nuevos por día se
pierden si pasan más de 30 días sin correr. Igual que en Brand Lift, el caché nunca se encoge.

Las métricas de página se piden con el token de la PÁGINA, que se obtiene de `me/accounts` con
el token del system user. Son ~7 llamadas por corrida.
"""
import datetime
import json
import os
import time

import sources_brand_lift as BL

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "social_cache.json")

# Clave = la misma que usa el tablero para la hoja de cada marca.
MARCAS = {
    "MX": {"nombre": "Tuhabi", "fb": "101289638870959", "ig": "17841448508205960"},
    "CO": {"nombre": "Habi", "fb": "120470019348648", "ig": "17841421889298348"},
    "PCOM": {"nombre": "Propiedades.com", "fb": "382083361865231", "ig": "17841416041613709"},
}
FB_METRICAS = ("page_follows", "page_daily_follows_unique", "page_daily_unfollows_unique")
FB_CAMPO = {"page_follows": "fb_total", "page_daily_follows_unique": "fb_altas",
            "page_daily_unfollows_unique": "fb_bajas"}
DIA = 86400


def _dia(end_time):
    """Meta fecha el valor diario con el `end_time` del corte (07:00 UTC del día SIGUIENTE).
    El día al que pertenece el dato es el anterior."""
    d = datetime.date.fromisoformat(end_time[:10]) - datetime.timedelta(days=1)
    return d.isoformat()


def _get(path, token, **params):
    return BL._get(path, access_token=token, **params)


def _token_paginas():
    """{page_id: page_token} de las páginas que ve el system user, + totales de hoy."""
    tokens = BL._tokens()
    if not tokens:
        return False, "sin token de Meta", {}
    ok, pl = _get("me/accounts", tokens[0][1], limit=50,
                  fields="id,access_token,followers_count,"
                         "instagram_business_account{id,followers_count}")
    if not ok:
        return False, (pl.get("error") or {}).get("message"), {}
    return True, None, {p["id"]: p for p in pl.get("data") or []}


def _fb_insights(page_id, page_token, desde, hasta):
    ok, pl = _get(f"{page_id}/insights", page_token, metric=",".join(FB_METRICAS),
                  period="day", since=desde, until=hasta)
    if not ok:
        raise RuntimeError((pl.get("error") or {}).get("message"))
    dias = {}
    for m in pl.get("data") or []:
        campo = FB_CAMPO.get(m.get("name"))
        for v in m.get("values") or []:
            d = _dia(v["end_time"])
            # El día en curso trae altas y bajas a medias: solo se guardan días cerrados.
            if campo and isinstance(v.get("value"), (int, float)) and d < datetime.date.today().isoformat():
                dias.setdefault(d, {})[campo] = v["value"]
    return dias


def _ig_nuevos(ig_id, token, desde, hasta, hoy):
    ok, pl = _get(f"{ig_id}/insights", token, metric="follower_count", period="day",
                  since=desde, until=hasta)
    if not ok:
        raise RuntimeError((pl.get("error") or {}).get("message"))
    dias = {}
    reciente = (datetime.date.fromisoformat(hoy) - datetime.timedelta(days=2)).isoformat()
    for m in pl.get("data") or []:
        for v in m.get("values") or []:
            d = _dia(v["end_time"])
            # Instagram publica los nuevos con ~2 días de atraso y mientras tanto devuelve 0. Un
            # cero reciente es "todavía no llega", no "nadie nos siguió": no se guarda, y la
            # siguiente corrida lo llena porque la ventana es de 30 días.
            if v.get("value") == 0 and d >= reciente:
                continue
            dias[d] = {"ig_nuevos": v.get("value")}
    return dias


def fetch(hoy=None):
    """Una corrida diaria. → (ok, {marca: {día: {campo: valor}}}, errores)
    `ok=False` solo si no se pudo ni listar las páginas; un fallo de una marca no tumba las otras
    y se informa en `errores`."""
    hoy = hoy or datetime.date.today().isoformat()
    ok, err, paginas = _token_paginas()
    if not ok:
        return False, {}, {"_": err}
    hasta = int(time.time())
    desde = hasta - 28 * DIA
    out, errores = {}, {}
    for clave, m in MARCAS.items():
        p = paginas.get(m["fb"])
        if not p:
            errores[clave] = f"el token no ve la página de Facebook de {m['nombre']}"
            continue
        dias = {}
        try:
            for d, v in _fb_insights(m["fb"], p.get("access_token"), desde, hasta).items():
                dias.setdefault(d, {}).update(v)
            ig = p.get("instagram_business_account") or {}
            if ig.get("id") == m["ig"]:
                for d, v in _ig_nuevos(m["ig"], BL._tokens()[0][1], desde, hasta, hoy).items():
                    dias.setdefault(d, {}).update(v)
                # La foto del total de Instagram es de HOY: no hay otra forma de tener su serie.
                dias.setdefault(hoy, {})["ig_total"] = ig.get("followers_count")
            else:
                errores[clave] = f"el token no ve el Instagram de {m['nombre']}"
        except RuntimeError as e:
            errores[clave] = str(e)
        out[clave] = dias
    return True, out, errores


def backfill_fb(dias=730):
    """Historia de Facebook hacia atrás, en ventanas de 89 días. SOLO A MANO.
    Uso: python3 -c "import sources_social as S; S.backfill_to_cache()"."""
    ok, err, paginas = _token_paginas()
    if not ok:
        raise RuntimeError(err)
    out = {}
    fin = int(time.time())
    for clave, m in MARCAS.items():
        p = paginas[m["fb"]]
        hasta = fin
        while hasta > fin - dias * DIA:
            # Meta responde a veces "unexpected error, retry later" en ventanas viejas: se
            # reintenta una vez y, si persiste, se corta la historia de esa marca ahí (lo ya
            # traído se conserva) en vez de perder el backfill entero.
            try:
                try:
                    dias_v = _fb_insights(m["fb"], p["access_token"], hasta - 89 * DIA, hasta)
                except RuntimeError:
                    time.sleep(5)
                    dias_v = _fb_insights(m["fb"], p["access_token"], hasta - 89 * DIA, hasta)
            except RuntimeError as e:
                print(f"backfill {clave}: se corta antes de "
                      f"{datetime.date.fromtimestamp(hasta).isoformat()} — {e}")
                break
            for d, v in dias_v.items():
                out.setdefault(clave, {}).setdefault(d, {}).update(v)
            hasta -= 89 * DIA
    return out


def backfill_to_cache():
    cache = load_cache()
    nuevo = merge(cache, backfill_fb())
    save_cache(nuevo["datos"], nuevo.get("last_refresh"))
    for k, v in nuevo["datos"].items():
        print(f"backfill {k}: {len(v)} días")


def load_cache():
    if not os.path.exists(CACHE):
        return {"datos": {}, "last_refresh": None}
    return json.loads(open(CACHE, encoding="utf-8").read())


def save_cache(datos, last_refresh):
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"datos": datos, "last_refresh": last_refresh}, f, ensure_ascii=False,
                  indent=1, sort_keys=True)
        f.write("\n")


def merge(cache, fresh):
    """Funde por (marca, día, campo). Lo nuevo pisa a lo viejo campo por campo; nada se borra."""
    datos = {k: {d: dict(v) for d, v in dias.items()} for k, dias in cache.get("datos", {}).items()}
    for k, dias in fresh.items():
        for d, v in dias.items():
            datos.setdefault(k, {}).setdefault(d, {}).update(v)
    return {"datos": datos, "last_refresh": cache.get("last_refresh")}


def series(datos, clave):
    """Filas diarias ordenadas: {date, fb_total, fb_altas, fb_bajas, ig_total, ig_nuevos}."""
    return [{"date": d, **v} for d, v in sorted((datos.get(clave) or {}).items())]
