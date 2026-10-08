"""La Rosa de Guadalupe (Tuhabi México): lo orgánico y lo pagado de la acción, en un data.json.

Tres fuentes, cada una aislada (si una falla, las otras se publican y la que falló sale "stale"
desde el caché):

1. **Pagado** — API de Meta, cuenta Tuhabi MX (USD). Los anuncios se reconocen por el NOMBRE
   (`Rosa_*`) y el filtro va del lado de Meta: nunca se recorren todos los anuncios de la cuenta,
   que el 6-oct-2026 se quedó sin cuota por hacerlo. Son 6 llamadas por corrida (ver `pagado()`).
   El objetivo se lee de la campaña, así que una campaña nueva (p. ej. de interacción) con
   anuncios `Rosa_*` aparece sola en el tablero.
   Los leads son los que reporta el píxel de Meta, no los del CRM: la tabla de UTM por lead
   (`papyrus-data-mx.habi_data_analytics.deal_utm`) no se actualiza desde el 16-sep-2026.
2. **Orgánico** — publicaciones de @tuhabimx y de la página de Tuhabi desde `inicio_organico` con
   🌹 / "rosa" / "guadalupe" en el texto, más los ids de `config.json` (`incluir` / `excluir`).
   Una llamada por post para sus métricas.
3. **Cuenta** — sin llamadas: lee `salud-marca/social_cache.json` (visitas al perfil, clics al
   sitio, seguidores nuevos por día y los posts de antes de la acción para el promedio).

Uso: `META_SYSTEM_USER_TOKEN=... python3 build.py`
"""
import datetime
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SALUD = os.path.join(os.path.dirname(HERE), "salud-marca")
sys.path.insert(0, SALUD)
import sources_brand_lift as BL  # noqa: E402
import sources_ig_posts as IGP  # noqa: E402
import sources_social as SOCIAL  # noqa: E402

CONFIG = os.path.join(HERE, "config.json")
CACHE = os.path.join(HERE, "cache.json")
DATA = os.path.join(HERE, "data.json")
MINIATURAS = os.path.join(HERE, "miniaturas")
SOCIAL_CACHE = os.path.join(SALUD, "social_cache.json")

IG_ID, PAGE_ID = SOCIAL.MARCAS["MX"]["ig"], SOCIAL.MARCAS["MX"]["fb"]

OBJETIVOS = {"OUTCOME_AWARENESS": "alcance", "OUTCOME_SALES": "leads", "OUTCOME_LEADS": "leads",
             "OUTCOME_ENGAGEMENT": "interaccion", "OUTCOME_TRAFFIC": "trafico"}

# action_type de Meta → nombre en el tablero. "post" es compartir (así lo llama Meta).
ACCIONES = {"link_click": "clics_link", "landing_page_view": "landing", "post_engagement": "interacciones",
            "post_reaction": "reacciones", "comment": "comentarios", "post": "compartidos",
            "onsite_conversion.post_save": "guardados", "video_view": "video_3s",
            "offsite_conversion.fb_pixel_lead": "leads"}
VIDEO = {"video_thruplay_watched_actions": "thruplay", "video_p25_watched_actions": "p25",
         "video_p50_watched_actions": "p50", "video_p75_watched_actions": "p75",
         "video_p100_watched_actions": "p100"}
SUMABLES = ("inversion", "impresiones", "clics", *ACCIONES.values(), *VIDEO.values(), "recordacion")
CAMPOS_AD = ("campaign_id,campaign_name,objective,adset_name,ad_id,ad_name,spend,impressions,reach,"
             "clicks,inline_link_clicks,actions,estimated_ad_recallers," + ",".join(VIDEO))
LIMITE = (4, 17, 32, 613, 80000, 80004)   # códigos de Meta de "demasiadas llamadas"


# ── utilidades ────────────────────────────────────────────────────────────────
def leer(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def escribir(ruta, obj):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def _token():
    t = BL._tokens()
    if not t:
        raise RuntimeError("sin token de Meta (META_SYSTEM_USER_TOKEN)")
    return t[0][1]


def _get(path, reintentos=2, **params):
    """BL._get con espera ante el límite de llamadas de la cuenta, y error legible."""
    params.setdefault("access_token", _token())
    for i in range(reintentos + 1):
        ok, pl = BL._get(path, **params)
        if ok:
            return pl
        err = pl.get("error") or {}
        if i < reintentos and (err.get("code") in LIMITE or err.get("is_transient")):
            time.sleep(30 * (i + 1))
            continue
        raise RuntimeError(f"Meta {path.split('/')[0]}: {err.get('code')} {err.get('message') or ''}"[:300])


def _todas(path, **params):
    """Todas las páginas de una lista de la API."""
    out, after = [], None
    while True:
        if after:
            params["after"] = after
        pl = _get(path, **params)
        out += pl.get("data") or []
        after = ((pl.get("paging") or {}).get("cursors") or {}).get("after")
        if not (pl.get("paging") or {}).get("next") or not after:
            return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ── pagado ────────────────────────────────────────────────────────────────────
def objetivo(obj):
    return OBJETIVOS.get(obj or "", "otro")


def pieza(nombre):
    """'Rosa_6_Instagram_Desempleado' y 'Rosa_6_Desempleado' son la misma pieza: el nombre sin la
    plataforma. → 'Rosa_6_Desempleado'."""
    partes = [p for p in (nombre or "").strip().split("_") if p.lower() not in ("facebook", "instagram", "fb", "ig")]
    return "_".join(partes)


def metricas_fila(f):
    """Una fila de insights de Meta → {métrica: número} con los nombres del tablero."""
    m = {k: 0.0 for k in SUMABLES}
    m["inversion"] = _num(f.get("spend"))
    m["impresiones"] = _num(f.get("impressions"))
    m["clics"] = _num(f.get("clicks"))
    m["recordacion"] = _num(f.get("estimated_ad_recallers"))
    for a in f.get("actions") or []:
        if a.get("action_type") in ACCIONES:
            m[ACCIONES[a["action_type"]]] = _num(a.get("value"))
    # Sin el evento de píxel explícito, "lead" es el mismo número (verificado el 7-oct: 407 = 407).
    if not m["leads"]:
        m["leads"] = sum(_num(a.get("value")) for a in f.get("actions") or [] if a.get("action_type") == "lead")
    if not m["clics_link"]:
        m["clics_link"] = _num(f.get("inline_link_clicks"))
    for campo, nombre in VIDEO.items():
        m[nombre] = sum(_num(a.get("value")) for a in f.get(campo) or [])
    return {k: round(v, 2) if k == "inversion" else int(v) for k, v in m.items() if v}


def sumar(filas):
    out = {}
    for f in filas:
        for k in SUMABLES:
            if f.get(k):
                out[k] = out.get(k, 0) + f[k]
    if "inversion" in out:
        out["inversion"] = round(out["inversion"], 2)
    return out


def comparativo(filas_rosa, filas_campana):
    """Por campaña: lo de los anuncios Rosa contra el resto de la MISMA campaña en los MISMOS días
    (los días con inversión en Rosa). `filas_campana` son totales diarios de la campaña entera."""
    out = []
    for cid in sorted({f["campana_id"] for f in filas_rosa}):
        rosa = [f for f in filas_rosa if f["campana_id"] == cid]
        dias = {f["d"] for f in rosa if f.get("inversion")}
        camp = [f for f in filas_campana if f["campana_id"] == cid and f["d"] in dias]
        r, c = sumar(rosa), sumar(camp)
        if not c:
            continue
        otros = {k: round(c.get(k, 0) - r.get(k, 0), 2) for k in SUMABLES if c.get(k, 0) - r.get(k, 0) > 0}
        out.append({"campana_id": cid, "campana": rosa[0]["campana"], "obj": rosa[0]["obj"],
                    "desde": min(dias) if dias else None, "hasta": max(dias) if dias else None,
                    "rosa": r, "otros": otros})
    return out


def _fila(f, extra=None):
    out = {"d": f.get("date_start"), "ad": f.get("ad_id"), "campana_id": f.get("campaign_id"),
           "campana": f.get("campaign_name"), "obj": objetivo(f.get("objective"))}
    out.update(extra or {})
    out.update(metricas_fila(f))
    return out


def pagado(cfg, hoy):
    """6 llamadas a la cuenta, todas filtradas por nombre o por campaña."""
    act, pref = cfg["cuenta_ads"], cfg["prefijo_ads"]
    tr = json.dumps({"since": cfg["inicio_pagado"], "until": hoy})
    filtro = json.dumps([{"field": "ad.name", "operator": "CONTAIN", "value": pref}])
    base = {"time_range": tr, "filtering": filtro, "limit": 500}

    # 1. Diario por anuncio: la base de casi todo.
    crudas = _todas(f"{act}/insights", level="ad", fields=CAMPOS_AD, time_increment=1, **base)
    crudas = [f for f in crudas if (f.get("ad_name") or "").lower().startswith(pref.lower())]
    filas = [_fila(f) for f in crudas]
    # 2. Por plataforma (Facebook / Instagram / otras), total por anuncio.
    plat = []
    for f in _todas(f"{act}/insights", level="ad", fields="ad_id,ad_name,spend,impressions,clicks,inline_link_clicks,actions",
                    breakdowns="publisher_platform", **base):
        if (f.get("ad_name") or "").lower().startswith(pref.lower()):
            p = f.get("publisher_platform")
            plat.append(dict(metricas_fila(f), ad=f.get("ad_id"), plat=p if p in ("facebook", "instagram") else "otras"))
    # 3 y 4. Alcance ÚNICO (no se puede sumar por día ni por anuncio): por campaña y total.
    alcance = {"total": {}, "campanas": {}}
    for f in _get(f"{act}/insights", level="campaign", fields="campaign_id,objective,reach,impressions", **base).get("data") or []:
        alcance["campanas"][f["campaign_id"]] = {"obj": objetivo(f.get("objective")), "alcance": int(_num(f.get("reach"))),
                                                 "impresiones": int(_num(f.get("impressions")))}
    for f in _get(f"{act}/insights", level="account", fields="reach,impressions", **base).get("data") or []:
        alcance["total"] = {"alcance": int(_num(f.get("reach"))), "impresiones": int(_num(f.get("impressions")))}
    # 5. Las campañas completas, para comparar Rosa contra el resto de sus anuncios.
    cids = sorted({f["campana_id"] for f in filas})
    filas_camp = []
    if cids:
        filtro_c = json.dumps([{"field": "campaign.id", "operator": "IN", "value": cids}])
        for f in _todas(f"{act}/insights", level="campaign", time_increment=1, time_range=tr, filtering=filtro_c, limit=500,
                        fields="campaign_id,campaign_name,objective,spend,impressions,clicks,inline_link_clicks,actions,"
                               "estimated_ad_recallers,video_thruplay_watched_actions"):
            filas_camp.append(_fila(f))
    # 6. Los anuncios: estado, fecha y miniatura del creativo.
    anuncios, imagenes = {}, {}
    for a in _todas(f"{act}/ads", fields="id,name,effective_status,created_time,campaign_id,creative{thumbnail_url}",
                    thumbnail_width=240, thumbnail_height=240, filtering=filtro, limit=100):
        if not (a.get("name") or "").lower().startswith(pref.lower()):
            continue
        anuncios[a["id"]] = {"nombre": a["name"], "pieza": pieza(a["name"]), "estado": a.get("effective_status"),
                             "creado": (a.get("created_time") or "")[:10], "campana_id": a.get("campaign_id")}
        imagenes[a["id"]] = (a.get("creative") or {}).get("thumbnail_url")
    for f in filas:   # anuncios con datos que ya no salen en la lista (borrados)
        a = next((x for x in crudas if x.get("ad_id") == f["ad"]), {})
        anuncios.setdefault(f["ad"], {"nombre": a.get("ad_name"), "pieza": pieza(a.get("ad_name")),
                                      "estado": "DELETED", "campana_id": f["campana_id"]})
    for i, a in anuncios.items():
        a["obj"] = next((f["obj"] for f in filas if f["ad"] == i), None) or \
            (alcance["campanas"].get(a.get("campana_id")) or {}).get("obj")
    return {"filas": filas, "plataforma": plat, "alcance": alcance, "anuncios": anuncios,
            "comparativo": comparativo(filas, filas_camp)}, imagenes


# ── orgánico ──────────────────────────────────────────────────────────────────
def es_rosa(texto, patron):
    return bool(re.search(patron, texto or "", re.I))


def clasificar(posts, cfg):
    """posts: [{id, fecha, texto_completo}] → los de la acción. `incluir` gana a todo; `excluir`
    gana a la regla."""
    inc, exc = set(cfg.get("incluir") or []), set(cfg.get("excluir") or [])
    return [p for p in posts if p["id"] in inc or
            (p["id"] not in exc and p["fecha"] >= cfg["inicio_organico"] and es_rosa(p.get("texto_completo"), cfg["patron"]))]


IG_CAMPOS = "id,timestamp,caption,permalink,media_type,media_product_type,like_count,comments_count,thumbnail_url,media_url"
IG_METRICAS = {"views": "vistas", "reach": "alcance", "saved": "guardados", "shares": "compartidos",
               "total_interactions": "interacciones", "likes": "likes", "comments": "comentarios",
               "ig_reels_avg_watch_time": "seg_promedio"}
FB_CAMPOS = ("id,created_time,status_type,permalink_url,message,full_picture,shares,"
             "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)")
FB_METRICAS = {"post_media_view": "vistas", "post_clicks": "clics", "post_video_views": "vistas_video",
               "post_video_avg_time_watched": "seg_promedio"}


def _insights(post_id, metricas, token):
    try:
        pl = _get(f"{post_id}/insights", reintentos=1, metric=",".join(metricas), access_token=token)
    except RuntimeError as e:
        print(f"WARN métricas {post_id}: {e}")
        return {}
    out = {}
    for d in pl.get("data") or []:
        if d.get("name") in metricas:
            v = (d.get("values") or [{}])[0].get("value")
            if isinstance(v, (int, float)):
                out[metricas[d["name"]]] = round(v / 1000, 1) if metricas[d["name"]] == "seg_promedio" else v
    return out


def organico(cfg):
    """→ (posts de la acción con métricas, {id: url imagen})."""
    tok = _token()
    ok, err, paginas = SOCIAL._token_paginas()
    if not ok:
        raise RuntimeError(f"tokens de página: {err}")
    ptok = (paginas.get(PAGE_ID) or {}).get("access_token")
    if not ptok:
        raise RuntimeError("el token no ve la página de Tuhabi")
    posts, imagenes = [], {}
    for x in _get(f"{IG_ID}/media", fields=IG_CAMPOS, limit=100, access_token=tok).get("data") or []:
        posts.append({"id": x["id"], "red": "ig", "fecha": x["timestamp"][:10], "link": x.get("permalink"),
                      "texto_completo": x.get("caption") or "", "formato": IGP.formato(x),
                      "likes": x.get("like_count") or 0, "comentarios": x.get("comments_count") or 0,
                      "_img": x.get("thumbnail_url") or x.get("media_url")})
    for x in _get(f"{PAGE_ID}/posts", fields=FB_CAMPOS, limit=100, access_token=ptok).get("data") or []:
        t = x.get("status_type") or ""
        posts.append({"id": x["id"], "red": "fb", "fecha": x["created_time"][:10], "link": x.get("permalink_url"),
                      "texto_completo": x.get("message") or "",
                      "formato": "video" if "video" in t else "foto" if "photo" in t else "texto",
                      "reacciones": ((x.get("reactions") or {}).get("summary") or {}).get("total_count") or 0,
                      "comentarios": ((x.get("comments") or {}).get("summary") or {}).get("total_count") or 0,
                      "compartidos": (x.get("shares") or {}).get("count") or 0, "_img": x.get("full_picture")})
    out = []
    for p in clasificar(posts, cfg):
        imagenes[p["id"]] = p.pop("_img")
        if p["red"] == "ig":
            p.update(_insights(p["id"], IG_METRICAS, tok))
        else:
            p.update(_insights(p["id"], FB_METRICAS, ptok))
            p["interacciones"] = p.get("reacciones", 0) + p.get("comentarios", 0) + p.get("compartidos", 0)
        p["texto"] = p.pop("texto_completo").strip().split("\n")[0][:160]
        out.append(p)
    return sorted(out, key=lambda p: p["fecha"], reverse=True), imagenes


def promedio_previo(social, inicio, dias=90):
    """Promedio por post de vistas, alcance e interacciones de lo publicado en los `dias` antes de
    la acción (posts normales). En Instagram deja fuera los que tuvieron pauta."""
    desde = (datetime.date.fromisoformat(inicio) - datetime.timedelta(days=dias)).isoformat()
    out = {"desde": desde, "hasta": inicio}
    for red, clave in (("ig", "posts"), ("fb", "fb_posts")):
        ps = [p for p in ((social.get(clave) or {}).get("MX") or {}).values()
              if desde <= p.get("fecha", "") < inicio and p.get("pauta") is not True and p.get("vistas")]
        if red == "fb":
            ps = [dict(p, interacciones=p.get("reacciones", 0) + p.get("comentarios", 0) + p.get("compartidos", 0)) for p in ps]
        r = {"n": len(ps)}
        for m in ("vistas", "alcance", "interacciones"):
            vals = [p[m] for p in ps if p.get(m) is not None]
            if vals:
                r[m] = round(sum(vals) / len(vals), 1)
                r[m + "_mediana"] = sorted(vals)[len(vals) // 2]
        out[red] = r
    return out


# ── efecto en la cuenta ───────────────────────────────────────────────────────
CUENTA = ("ig_perfil_d", "ig_clics_d", "ig_altas_d", "ig_vistas_d", "ig_inter_d", "fb_visitas", "fb_altas", "fb_vistas", "fb_inter")


def cuenta(social, inicio, hoy, dias_antes=14, dias_serie=35):
    datos = (social.get("datos") or {}).get("MX") or {}
    ini = datetime.date.fromisoformat(inicio)
    antes = ((ini - datetime.timedelta(days=dias_antes)).isoformat(), (ini - datetime.timedelta(days=1)).isoformat())
    serie_desde = (ini - datetime.timedelta(days=dias_serie)).isoformat()
    dias = sorted(d for d in datos if serie_desde <= d <= hoy)
    serie = {k: [datos[d].get(k) for d in dias] for k in CUENTA}

    def prom(a, b, k):
        vals = [datos[d][k] for d in datos if a <= d <= b and datos[d].get(k) is not None]
        return {"prom": round(sum(vals) / len(vals), 1), "dias": len(vals), "total": sum(vals)} if vals else None

    periodos = {k: {"antes": prom(*antes, k), "despues": prom(inicio, hoy, k)} for k in CUENTA}
    return {"dias": dias, "serie": serie, "periodos": periodos, "antes": antes, "despues": (inicio, hoy)}


# ── armado ────────────────────────────────────────────────────────────────────
def _seccion(nombre, fn, cache, ahora):
    """Corre una fuente; si falla, devuelve la del caché como 'stale' con la razón."""
    try:
        val = fn()
        return {"status": "ok", "last_updated": ahora, **val}, None
    except Exception as e:  # noqa: BLE001 — cualquier falla de una fuente no tumba a las otras
        razon = f"{type(e).__name__}: {e}"[:300]
        print(f"ERROR {nombre}: {razon}")
        previo = cache.get(nombre)
        if previo:
            return {**previo, "status": "stale", "reason": razon}, e
        return {"status": "error", "reason": razon}, e


def build(hoy=None, ahora=None):
    cfg = leer(CONFIG, {})
    hoy = hoy or datetime.date.today().isoformat()
    ahora = ahora or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cache = leer(CACHE, {})
    social = leer(SOCIAL_CACHE, {})
    imagenes = {}

    def _pagado():
        val, imgs = pagado(cfg, hoy)
        imagenes.update(imgs)
        return val

    def _organico():
        posts, imgs = organico(cfg)
        imagenes.update(imgs)
        historia = cache.get("historia") or {}
        for p in posts:   # foto diaria de cada post, para ver cómo crecen
            historia.setdefault(p["id"], {})[hoy] = {k: p.get(k) for k in ("vistas", "alcance", "interacciones") if p.get(k) is not None}
        cache["historia"] = historia
        return {"posts": posts, "promedio": promedio_previo(social, cfg["inicio_organico"])}

    def _cuenta():
        if not social:
            raise RuntimeError("no se pudo leer salud-marca/social_cache.json")
        return cuenta(social, cfg["inicio_organico"], hoy)

    out = {"generated_at": ahora, "config": {k: cfg.get(k) for k in ("inicio_organico", "inicio_pagado", "patron", "prefijo_ads")}}
    for nombre, fn in (("pagado", _pagado), ("organico", _organico), ("cuenta", _cuenta)):
        out[nombre], _ = _seccion(nombre, fn, cache, ahora)
        if out[nombre]["status"] == "ok":
            cache[nombre] = out[nombre]

    # Miniaturas de anuncios y posts (una carpeta; se borran las que ya no salen).
    ids = [{"id": i} for i in (out["pagado"].get("anuncios") or {})] + \
          [{"id": p["id"]} for p in (out["organico"].get("posts") or [])]
    con = IGP.miniaturas([ids], imagenes, carpeta=MINIATURAS) if ids else set()
    for i, a in (out["pagado"].get("anuncios") or {}).items():
        a["mini"] = i in con
    for p in out["organico"].get("posts") or []:
        p["mini"] = p["id"] in con
    out["historia"] = cache.get("historia") or {}

    escribir(CACHE, cache)
    escribir(DATA, out)
    return out


if __name__ == "__main__":
    d = build()
    pg = d["pagado"]
    print(f"pagado: {pg['status']} · {len(pg.get('filas') or [])} filas · {len(pg.get('anuncios') or {})} anuncios")
    print(f"orgánico: {d['organico']['status']} · {len(d['organico'].get('posts') or [])} posts")
    print(f"cuenta: {d['cuenta']['status']}")
