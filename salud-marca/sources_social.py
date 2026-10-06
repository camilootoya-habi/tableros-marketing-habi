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
# `page_follows` (el total) solo es real desde este día: antes Meta devuelve un valor CONGELADO
# (el mismo número en 2019, 2021 y jul-2024, verificado el 5-oct-2026). Las altas y bajas
# diarias sí son reales hacia atrás (al menos desde 2021), así que el total anterior se
# reconstruye con ellas en `series()`: en 2 años, altas − bajas difiere del cambio real del
# total en menos de 1% (Habi: +4.569 contra +4.544).
FB_TOTAL_DESDE = "2024-10-04"


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
            if campo == "fb_total" and d < FB_TOTAL_DESDE:
                continue   # total congelado, no real
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


def _ts(d):
    return int(datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc).timestamp())


def _mes_siguiente(d):
    return datetime.date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _ig_mes(ig_id, token, ini, ahora=None):
    """Métricas de Instagram de UN mes (`ini` = día 1). La API no acepta ventanas de más de 30
    días, así que el mes va en dos mitades y se suma (todas son conteos aditivos). El mes en
    curso se corta en `ahora`.

    Historia real verificada el 6-oct-2026 en @tuhabimx: altas y bajas desde ~oct-2025; vistas e
    interacciones desde ~ago-2025. Antes de eso la API no da error sino CEROS e interacciones
    NEGATIVAS (−5, −2): se descartan en vez de guardarse como un mes sin actividad."""
    ahora = ahora or int(time.time())
    mitad, fin = ini.replace(day=16), _mes_siguiente(ini)
    tot, mitades_con_follows, mitades = {}, 0, 0
    for a, b in ((ini, mitad), (mitad, fin)):
        desde, hasta = _ts(a), min(_ts(b), ahora)
        if desde >= hasta:
            continue
        ok, pl = _get(f"{ig_id}/insights", token, metric="follows_and_unfollows", period="day",
                      metric_type="total_value", breakdown="follow_type", since=desde, until=hasta)
        if not ok:
            raise RuntimeError((pl.get("error") or {}).get("message"))
        mitades += 1
        hubo = False
        for d in pl.get("data") or []:
            for bd in (d.get("total_value") or {}).get("breakdowns") or []:
                for x in bd.get("results") or []:
                    # FOLLOWER = empezó a seguir; NON_FOLLOWER = dejó de seguir. Verificado: la
                    # suma de FOLLOWER en 28 días es igual a la de `follower_count` diario (609).
                    campo = {"FOLLOWER": "ig_altas", "NON_FOLLOWER": "ig_bajas"}.get(x["dimension_values"][0])
                    if campo:
                        tot[campo] = tot.get(campo, 0) + x["value"]
                        hubo = True
        mitades_con_follows += hubo
        ok, pl = _get(f"{ig_id}/insights", token, metric="views,total_interactions,website_clicks,profile_views",
                      period="day", metric_type="total_value", since=desde, until=hasta)
        if not ok:
            raise RuntimeError((pl.get("error") or {}).get("message"))
        for d in pl.get("data") or []:
            campo = {"views": "ig_vistas", "total_interactions": "ig_interacciones",
                     "website_clicks": "ig_clics", "profile_views": "ig_perfil"}.get(d.get("name"))
            if campo:
                tot[campo] = tot.get(campo, 0) + ((d.get("total_value") or {}).get("value") or 0)
    # Altas y bajas solo si TODAS las mitades consultadas trajeron dato: el mes en que empieza la
    # historia (sep-2025) trae solo la segunda mitad y se leería como un mes sin crecimiento.
    if mitades_con_follows < mitades:
        tot.pop("ig_altas", None), tot.pop("ig_bajas", None)
    # Vistas e interacciones van juntas: antes de ago-2025 la API da vistas en 0 o 1 con
    # interacciones en 0 o negativas. Sin interacciones reales, ninguna de las dos cuenta.
    if (tot.get("ig_interacciones") or 0) <= 0:
        tot.pop("ig_interacciones", None), tot.pop("ig_vistas", None)
    for k in ("ig_clics", "ig_perfil"):
        if not tot.get(k):
            tot.pop(k, None)
    return tot


def fetch_ig_meses(paginas=None, meses=2, ahora=None):
    """{marca: {AAAA-MM: métricas}} de los últimos `meses` meses (el en curso incluido). El cron
    pide 2: el mes en curso y el anterior, que todavía se corrige los primeros días."""
    tokens = BL._tokens()
    if not tokens:
        raise RuntimeError("sin token de Meta")
    hoy = datetime.date.fromtimestamp(ahora) if ahora else datetime.date.today()
    inicios, d = [], hoy.replace(day=1)
    for _ in range(meses):
        inicios.append(d)
        d = (d - datetime.timedelta(days=1)).replace(day=1)
    out = {}
    for clave, m in MARCAS.items():
        for ini in inicios:
            v = _ig_mes(m["ig"], tokens[0][1], ini, ahora)
            if v:
                out.setdefault(clave, {})[ini.isoformat()[:7]] = v
    return out


def fetch(hoy=None):
    """Una corrida diaria. → (ok, {marca: {día: {campo: valor}}}, errores)
    `ok=False` solo si no se pudo ni listar las páginas; un fallo de una marca no tumba las otras
    y se informa en `errores`. Las métricas MENSUALES de Instagram van aparte: `fetch_ig_meses`."""
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


def backfill_fb(dias=365 * 7):
    """Historia de Facebook hacia atrás, en ventanas de 89 días. SOLO A MANO.
    Se detiene en la primera ventana sin una sola alta ni baja: antes de eso la página no tenía
    datos (en las tres marcas, hacia 2019-2020).
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
            # Meta responde a ratos "unexpected error, retry later", más en ventanas largas: van
            # de 30 días con 3 reintentos y espera creciente. Si persiste, se corta la historia de
            # esa marca ahí (lo traído se conserva y volver a correr el backfill la completa).
            dias_v, error = None, None
            for intento in range(4):
                try:
                    dias_v = _fb_insights(m["fb"], p["access_token"], hasta - 30 * DIA, hasta)
                    break
                except RuntimeError as e:
                    error = e
                    time.sleep(5 * (intento + 1))
            if dias_v is None:
                print(f"backfill {clave}: se corta antes de "
                      f"{datetime.date.fromtimestamp(hasta).isoformat()} — {error}")
                break
            if not any((v.get("fb_altas") or 0) + (v.get("fb_bajas") or 0) for v in dias_v.values()):
                print(f"backfill {clave}: sin altas ni bajas antes de "
                      f"{datetime.date.fromtimestamp(hasta).isoformat()}, fin de la historia")
                break
            for d, v in dias_v.items():
                out.setdefault(clave, {}).setdefault(d, {}).update(v)
            hasta -= 30 * DIA
    return out


def backfill_to_cache():
    cache = load_cache()
    nuevo = merge(cache, backfill_fb())
    save_cache(nuevo["datos"], nuevo.get("last_refresh"), nuevo.get("ig_mes"))
    for k, v in nuevo["datos"].items():
        print(f"backfill {k}: {len(v)} días")


def backfill_ig_to_cache(meses=24):
    """Métricas mensuales de Instagram hacia atrás (la API da hasta 2 años). SOLO A MANO.
    Uso: python3 -c "import sources_social as S; S.backfill_ig_to_cache()"."""
    cache = load_cache()
    nuevo = merge_ig(cache, fetch_ig_meses(meses=meses))
    save_cache(nuevo["datos"], nuevo.get("last_refresh"), nuevo.get("ig_mes"))
    for k, v in nuevo["ig_mes"].items():
        print(f"backfill IG {k}: {len(v)} meses, desde {min(v)}")


def load_cache():
    if not os.path.exists(CACHE):
        return {"datos": {}, "ig_mes": {}, "last_refresh": None}
    c = json.loads(open(CACHE, encoding="utf-8").read())
    c.setdefault("ig_mes", {})
    return c


def save_cache(datos, last_refresh, ig_mes=None):
    """`ig_mes` = métricas MENSUALES de Instagram por marca (la API no las da por día)."""
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"datos": datos, "ig_mes": ig_mes or {}, "last_refresh": last_refresh}, f,
                  ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


def merge(cache, fresh):
    """Funde por (marca, día, campo). Lo nuevo pisa a lo viejo campo por campo; nada se borra."""
    datos = {k: {d: dict(v) for d, v in dias.items()} for k, dias in cache.get("datos", {}).items()}
    for k, dias in fresh.items():
        for d, v in dias.items():
            datos.setdefault(k, {}).setdefault(d, {}).update(v)
    return {"datos": datos, "ig_mes": cache.get("ig_mes", {}), "last_refresh": cache.get("last_refresh")}


def merge_ig(cache, fresh_meses):
    """Igual que `merge`, para las métricas mensuales de Instagram: por (marca, mes, campo)."""
    ig = {k: {m: dict(v) for m, v in meses.items()} for k, meses in cache.get("ig_mes", {}).items()}
    for k, meses in fresh_meses.items():
        for m, v in meses.items():
            ig.setdefault(k, {}).setdefault(m, {}).update(v)
    return {"datos": cache.get("datos", {}), "ig_mes": ig, "last_refresh": cache.get("last_refresh")}


def series(datos, clave):
    """Filas diarias ordenadas: {date, fb_total, fb_total_est, fb_altas, fb_bajas, ig_total,
    ig_nuevos}. `fb_total_est` es el total reconstruido hacia atrás desde el primer total real:
    total(d − 1) = total(d) − altas(d) + bajas(d). Va en un campo aparte para que el tablero lo
    dibuje distinto y nunca se confunda con un dato que Meta midió."""
    filas = [{"date": d, **{k: x for k, x in v.items() if not (k == "fb_total" and d < FB_TOTAL_DESDE)}}
             for d, v in sorted((datos.get(clave) or {}).items())]
    primero = next((i for i, r in enumerate(filas) if r.get("fb_total") is not None), None)
    if primero:
        total = filas[primero]["fb_total"]
        for i in range(primero, 0, -1):
            r = filas[i]
            if r.get("fb_altas") is None:
                break   # hueco en las altas: no se puede seguir reconstruyendo
            total = total - r["fb_altas"] + (r.get("fb_bajas") or 0)
            filas[i - 1]["fb_total_est"] = total
    return filas


def mensual(filas, ig_mes=None):
    """Una fila por mes. Totales = el ÚLTIMO del mes (foto de cierre); altas, bajas y nuevos =
    la SUMA. `dias_*` dice cuántos días aportaron, para marcar meses incompletos (el en curso,
    o el primero de Instagram) en vez de leerlos como una caída.

    `ig_mes` agrega las métricas mensuales de Instagram (altas, bajas, vistas, interacciones,
    clics, visitas al perfil) y con ellas reconstruye `ig_total_est`: el total de Instagram al
    cierre de cada mes anterior, hacia atrás desde la última foto real:
    cierre(m − 1) = cierre(m) − altas(m) + bajas(m). Mismo método que Facebook, pero SIN validar
    contra un total medido: Meta nunca dio la historia del total de Instagram."""
    out = {}
    for mes, v in (ig_mes or {}).items():
        out.setdefault(mes, {"month": mes, "fb_altas": 0, "fb_bajas": 0, "ig_nuevos": 0,
                             "dias_fb": 0, "dias_ig": 0}).update(v)
    for r in filas:
        m = out.setdefault(r["date"][:7], {"month": r["date"][:7], "fb_altas": 0, "fb_bajas": 0,
                                            "ig_nuevos": 0, "dias_fb": 0, "dias_ig": 0})
        for k in ("fb_total", "fb_total_est", "ig_total"):
            if r.get(k) is not None:
                m[k] = r[k]
        if r.get("fb_altas") is not None:
            m["fb_altas"] += r["fb_altas"]
            m["fb_bajas"] += r.get("fb_bajas") or 0
            m["dias_fb"] += 1
        if r.get("ig_nuevos") is not None:
            m["ig_nuevos"] += r["ig_nuevos"]
            m["dias_ig"] += 1
    meses = [out[k] for k in sorted(out)]
    ult = next((i for i in range(len(meses) - 1, -1, -1) if meses[i].get("ig_total") is not None), None)
    if ult is not None:
        cierre = meses[ult]["ig_total"]
        for i in range(ult, 0, -1):
            r = meses[i]
            if r.get("ig_altas") is None:
                break   # sin altas y bajas ese mes no se puede seguir hacia atrás
            cierre = cierre - r["ig_altas"] + (r.get("ig_bajas") or 0)
            meses[i - 1]["ig_total_est"] = cierre
    return meses
