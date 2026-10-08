"""La Rosa de Guadalupe (Tuhabi México): lo orgánico y lo pagado de la acción, en un data.json.

Tres fuentes, cada una aislada (si una falla, las otras se publican y la que falló sale "stale"
desde el caché):

1. **Pagado** — API de Meta, cuenta Tuhabi MX (USD). Los anuncios se reconocen por el NOMBRE
   (`Rosa_*`) y el filtro va del lado de Meta: nunca se recorren todos los anuncios de la cuenta,
   que el 6-oct-2026 se quedó sin cuota por hacerlo. Son 7 llamadas por corrida (ver `pagado()`).
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
import io
import json
import os
import re
import sys
import time
from urllib.request import urlopen

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
            "offsite_conversion.fb_pixel_lead": "leads", "offsite_conversion.fb_pixel_purchase": "compras",
            "offsite_conversion.fb_pixel_complete_registration": "registros",
            "onsite_conversion.post_unlike": "unlikes"}
# Atribución por vista (vio el anuncio, no le dio clic, y convirtió en 1 día): se separa porque es la
# parte más discutible de lo que Meta se atribuye.
POR_VISTA = {"leads": "leads_vista", "compras": "compras_vista"}
VIDEO = {"video_thruplay_watched_actions": "thruplay", "video_p25_watched_actions": "p25",
         "video_p50_watched_actions": "p50", "video_p75_watched_actions": "p75",
         "video_p100_watched_actions": "p100"}
SUMABLES = ("inversion", "impresiones", "clics", *ACCIONES.values(), *VIDEO.values(), "recordacion",
            *POR_VISTA.values(), "valor_compras")
VENTANAS = json.dumps(["7d_click", "1d_view"])
# Lo que optimiza Meta en cada conjunto: optimization_goal → texto del tablero.
OPTIMIZA = {"AD_RECALL_LIFT": "Recordación del anuncio", "REACH": "Alcance", "IMPRESSIONS": "Impresiones",
            "VALUE": "Valor de la conversión", "OFFSITE_CONVERSIONS": "Conversiones en el sitio",
            "LEAD_GENERATION": "Leads (formulario de Meta)", "LINK_CLICKS": "Clics en el enlace",
            "LANDING_PAGE_VIEWS": "Visitas a la landing", "POST_ENGAGEMENT": "Interacción con la publicación",
            "THRUPLAY": "ThruPlays"}
CAMPOS_AD = ("campaign_id,campaign_name,objective,adset_name,ad_id,ad_name,spend,impressions,reach,"
             "clicks,inline_link_clicks,actions,action_values,estimated_ad_recallers," + ",".join(VIDEO))
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
            nombre = ACCIONES[a["action_type"]]
            m[nombre] = _num(a.get("value"))
            if nombre in POR_VISTA:
                m[POR_VISTA[nombre]] = _num(a.get("1d_view"))
    for a in f.get("action_values") or []:
        if a.get("action_type") == "offsite_conversion.fb_pixel_purchase":
            m["valor_compras"] = _num(a.get("value"))
    # Sin el evento de píxel explícito, "lead" es el mismo número (verificado el 7-oct: 407 = 407).
    if not m["leads"]:
        m["leads"] = sum(_num(a.get("value")) for a in f.get("actions") or [] if a.get("action_type") == "lead")
    if not m["clics_link"]:
        m["clics_link"] = _num(f.get("inline_link_clicks"))
    for campo, nombre in VIDEO.items():
        m[nombre] = sum(_num(a.get("value")) for a in f.get(campo) or [])
    return {k: round(v, 2) if k in ("inversion", "valor_compras") else int(v) for k, v in m.items() if v}


def sumar(filas):
    out = {}
    for f in filas:
        for k in SUMABLES:
            if f.get(k):
                out[k] = out.get(k, 0) + f[k]
    for k in ("inversion", "valor_compras"):
        if k in out:
            out[k] = round(out[k], 2)
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
    """7 llamadas a la cuenta, todas filtradas por nombre o por campaña."""
    act, pref = cfg["cuenta_ads"], cfg["prefijo_ads"]
    tr = json.dumps({"since": cfg["inicio_pagado"], "until": hoy})
    filtro = json.dumps([{"field": "ad.name", "operator": "CONTAIN", "value": pref}])
    base = {"time_range": tr, "filtering": filtro, "limit": 500}

    # 1. Diario por anuncio: la base de casi todo.
    crudas = _todas(f"{act}/insights", level="ad", fields=CAMPOS_AD, time_increment=1,
                    action_attribution_windows=VENTANAS, **base)
    crudas = [f for f in crudas if (f.get("ad_name") or "").lower().startswith(pref.lower())]
    filas = [_fila(f) for f in crudas]
    # 2. Por plataforma y posición (Reels, Historias, Feed…), total por anuncio. La vista por
    # plataforma se arma sumando posiciones.
    plat = []
    for f in _todas(f"{act}/insights", level="ad", breakdowns="publisher_platform,platform_position",
                    fields="ad_id,ad_name,spend,impressions,clicks,inline_link_clicks,actions,estimated_ad_recallers,"
                           "video_thruplay_watched_actions", action_attribution_windows=VENTANAS, **base):
        if (f.get("ad_name") or "").lower().startswith(pref.lower()):
            p = f.get("publisher_platform")
            plat.append(dict(metricas_fila(f), ad=f.get("ad_id"), plat=p if p in ("facebook", "instagram") else "otras",
                             red=p, pos=f.get("platform_position")))
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
                        action_attribution_windows=VENTANAS,
                        fields="campaign_id,campaign_name,objective,spend,impressions,clicks,inline_link_clicks,actions,action_values,"
                               "estimated_ad_recallers,video_thruplay_watched_actions"):
            filas_camp.append(_fila(f))
    # 6. Los conjuntos de esas campañas: a qué evento optimiza Meta y con qué atribución.
    optimizacion = {}
    if cids:
        for s in _todas(f"{act}/adsets", fields="campaign_id,name,optimization_goal,promoted_object,attribution_spec,effective_status",
                        filtering=json.dumps([{"field": "campaign.id", "operator": "IN", "value": cids}]), limit=100):
            optimizacion.setdefault(s["campaign_id"], []).append(optimizacion_de(s))
    # 7. Los anuncios: estado, fecha, vista previa y creativo. La imagen NO sale de `thumbnail_url`:
    # Meta la da a 64 px pida el tamaño que se pida (verificado el 8-oct). Sale de la publicación de
    # Instagram del creativo (1080 px) o de la portada del video, y solo se pide si falta en el repo.
    anuncios, imagenes = {}, {}
    for a in _todas(f"{act}/ads", fields="id,name,effective_status,created_time,campaign_id,preview_shareable_link,"
                                         "creative{thumbnail_url,instagram_permalink_url,object_type,"
                                         "effective_instagram_media_id,video_id,image_url}",
                    filtering=filtro, limit=100):
        if not (a.get("name") or "").lower().startswith(pref.lower()):
            continue
        cr = a.get("creative") or {}
        anuncios[a["id"]] = {"nombre": a["name"], "pieza": pieza(a["name"]), "estado": a.get("effective_status"),
                             "creado": (a.get("created_time") or "")[:10], "campana_id": a.get("campaign_id"),
                             "preview": a.get("preview_shareable_link"), "ig": cr.get("instagram_permalink_url"),
                             "tipo": cr.get("object_type")}
        imagenes[a["id"]] = lambda cr=cr: imagen_creativo(cr)
    for f in filas:   # anuncios con datos que ya no salen en la lista (borrados)
        a = next((x for x in crudas if x.get("ad_id") == f["ad"]), {})
        anuncios.setdefault(f["ad"], {"nombre": a.get("ad_name"), "pieza": pieza(a.get("ad_name")),
                                      "estado": "DELETED", "campana_id": f["campana_id"]})
    for i, a in anuncios.items():
        a["obj"] = next((f["obj"] for f in filas if f["ad"] == i), None) or \
            (alcance["campanas"].get(a.get("campana_id")) or {}).get("obj")
    return {"filas": filas, "plataforma": plat, "alcance": alcance, "anuncios": anuncios,
            "optimizacion": optimizacion, "comparativo": comparativo(filas, filas_camp)}, imagenes


def imagen_creativo(cr):
    """URL de la imagen grande de un creativo: su post de Instagram, la portada del video, la imagen
    del anuncio o, si no hay otra, la miniatura de 64 px."""
    if cr.get("effective_instagram_media_id"):
        try:
            m = _get(cr["effective_instagram_media_id"], reintentos=0, fields="thumbnail_url,media_url,media_type")
            u = m.get("thumbnail_url") if m.get("media_type") == "VIDEO" else m.get("media_url") or m.get("thumbnail_url")
            if u:
                return u
        except RuntimeError as e:
            print(f"WARN imagen IG {cr['effective_instagram_media_id']}: {e}")
    if cr.get("video_id"):
        try:
            v = _get(cr["video_id"], reintentos=0, fields="thumbnails{uri,width,is_preferred}")
            ths = sorted((v.get("thumbnails") or {}).get("data") or [], key=lambda x: (not x.get("is_preferred"), -(x.get("width") or 0)))
            if ths:
                return ths[0]["uri"]
        except RuntimeError as e:
            print(f"WARN portada video {cr['video_id']}: {e}")
    return cr.get("image_url") or cr.get("thumbnail_url")


def _chica(ruta, minimo=100):
    """¿La imagen guardada es una miniatura de 64 px de las que da Meta? Entonces se vuelve a bajar."""
    try:
        from PIL import Image
        return max(Image.open(ruta).size) < minimo
    except Exception:  # noqa: BLE001 — sin Pillow o archivo roto: no se fuerza nada
        return False


def optimizacion_de(s):
    """Un conjunto de anuncios → {meta, evento, atribucion, estado} en palabras."""
    po = s.get("promoted_object") or {}
    ventanas = []
    for a in s.get("attribution_spec") or []:
        tipo = {"CLICK_THROUGH": "clic", "VIEW_THROUGH": "vista", "ENGAGED_VIDEO_VIEW": "video visto"}.get(a.get("event_type"), a.get("event_type"))
        ventanas.append(f"{a.get('window_days')} día{'' if a.get('window_days') == 1 else 's'} {tipo}")
    return {"conjunto": s.get("name"), "meta": OPTIMIZA.get(s.get("optimization_goal"), s.get("optimization_goal")),
            "goal": s.get("optimization_goal"), "evento": po.get("custom_event_type"),
            "atribucion": " + ".join(ventanas), "estado": s.get("effective_status")}


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
            p.update(_fb_post_ads(p["id"], ptok))
            p.update(_fb_reacciones(p["id"], ptok))
        p["texto"] = p.pop("texto_completo").strip().split("\n")[0][:160]
        out.append(p)
    return sorted(out, key=lambda p: p["fecha"], reverse=True), imagenes


def _fb_post_ads(post_id, token):
    """{vistas_org, vistas_ads} de un post de FB (`post_media_view` por `is_from_ads`)."""
    try:
        pl = _get(f"{post_id}/insights", reintentos=0, metric="post_media_view", breakdown="is_from_ads", access_token=token)
    except RuntimeError as e:
        print(f"WARN vistas por origen {post_id}: {e}")
        return {}
    out = {}
    for d in pl.get("data") or []:
        for v in d.get("values") or []:
            k = {"0": "vistas_org", "1": "vistas_ads"}.get(str(v.get("is_from_ads")))
            if k and isinstance(v.get("value"), (int, float)):
                out[k] = out.get(k, 0) + v["value"]
    return out


# Reacciones de Facebook: negativas = me entristece y me enoja (decisión de Camilo, 8-oct). En IG no
# existen tipos de reacción.
NEGATIVAS = {"sorry", "anger"}


def _fb_reacciones(post_id, token):
    """{r_like, r_love, ...} de por vida de un post de FB."""
    try:
        pl = _get(f"{post_id}/insights", reintentos=0, metric="post_reactions_by_type_total", access_token=token)
    except RuntimeError as e:
        print(f"WARN reacciones {post_id}: {e}")
        return {}
    v = (((pl.get("data") or [{}])[0].get("values") or [{}])[0]).get("value") or {}
    return {f"r_{k}": n for k, n in v.items() if isinstance(n, (int, float))} if isinstance(v, dict) else {}


def tono(reacciones):
    """{tipo: n} → (positivas, negativas)."""
    pos = sum(n for k, n in reacciones.items() if k not in NEGATIVAS)
    return pos, sum(n for k, n in reacciones.items() if k in NEGATIVAS)


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


# ── lo orgánico de toda la cuenta ─────────────────────────────────────────────
# Las vistas e interacciones "de la cuenta" que da Meta son ~99% anuncios (verificado el 8-oct:
# IG 5-oct 571 mil vistas AD contra ~5.5 mil orgánicas; FB 6-oct 1.39 M contra 3,354). Aquí se separan.
# IG: una llamada por día con desglose por formato (REEL/POST/STORY/CAROUSEL_CONTAINER/AD...).
# FB: la serie diaria de vistas con `is_from_ads` en una llamada; el alcance y las interacciones de la
# página ignoran ese desglose, así que de FB no hay alcance ni interacciones orgánicas diarias.
FORMATOS_IG = {"REEL": "reel", "POST": "post", "STORY": "story", "CAROUSEL_CONTAINER": "carrusel"}
IG_DIA = {"views": "vistas", "reach": "alcance", "total_interactions": "inter", "likes": "likes",
          "comments": "comentarios", "shares": "compartidos", "saves": "guardados"}
# Si un día del caché no tiene este campo es de una versión anterior y se vuelve a pedir.
IG_CAMPO_VERSION = "altas"
DIAS_IG_RECIENTES = 3   # Meta corrige los días recientes con uno o dos días de atraso


def ig_dia(fecha, token):
    """Un día de la cuenta de IG → {vistas_org, vistas_ads, vistas_reel, ..., alcance_org, inter_org, ...}.
    Orgánico = todo lo que no es AD (los formatos raros —foto de perfil, IGTV— suman al orgánico)."""
    # Meta cierra el día D a las 07:00 UTC de D+1 y `total_value` toma los cortes que caen en la
    # ventana: para el día D se pide [D+1, D+2) en UTC. Con [D, D+1) devuelve el día ANTERIOR
    # (verificado el 8-oct contra la serie diaria de `reach`: 225,252 es el 4-oct, 205,223 el 5-oct).
    d = datetime.date.fromisoformat(fecha) + datetime.timedelta(days=1)
    ventana = dict(period="day", metric_type="total_value", since=SOCIAL._ts(d),
                   until=SOCIAL._ts(d + datetime.timedelta(days=1)), access_token=token)
    pl = _get(f"{IG_ID}/insights", metric=",".join(IG_DIA), breakdown="media_product_type", **ventana)
    out = {}
    # Altas y bajas: Meta no las separa entre pauta y orgánico.
    seg = _get(f"{IG_ID}/insights", metric="follows_and_unfollows", breakdown="follow_type", **ventana)
    for m in seg.get("data") or []:
        for bd in (m.get("total_value") or {}).get("breakdowns") or []:
            for x in bd.get("results") or []:
                k = {"FOLLOWER": "altas", "NON_FOLLOWER": "bajas"}.get(x["dimension_values"][0])
                if k:
                    out[k] = x.get("value") or 0
    out.setdefault("altas", 0)
    out.setdefault("bajas", 0)
    for m in pl.get("data") or []:
        base = IG_DIA.get(m.get("name"))
        if not base:
            continue
        org = ads = 0
        for bd in (m.get("total_value") or {}).get("breakdowns") or []:
            for x in bd.get("results") or []:
                tipo, v = x["dimension_values"][0], x.get("value") or 0
                if tipo == "AD":
                    ads += v
                else:
                    org += v
                    if tipo in FORMATOS_IG:
                        out[f"{base}_{FORMATOS_IG[tipo]}"] = out.get(f"{base}_{FORMATOS_IG[tipo]}", 0) + v
        out[f"{base}_org"], out[f"{base}_ads"] = org, ads
    return out


def ultimo_cerrado(ahora_utc=None):
    """El último día que Meta ya cerró: el día D cierra a las 07:00 UTC de D+1."""
    ahora_utc = ahora_utc or datetime.datetime.now(datetime.timezone.utc)
    return ((ahora_utc - datetime.timedelta(hours=7)).date() - datetime.timedelta(days=1)).isoformat()


def dias_ig_a_pedir(guardados, desde, hasta):
    """Los días entre `desde` y `hasta` que faltan en el caché (o son de una versión anterior), más
    los últimos días recientes."""
    todos, d = [], datetime.date.fromisoformat(desde)
    while d <= datetime.date.fromisoformat(hasta):
        todos.append(d.isoformat())
        d += datetime.timedelta(days=1)
    recientes = set(todos[-DIAS_IG_RECIENTES:])
    return [f for f in todos if f not in guardados or IG_CAMPO_VERSION not in guardados[f] or f in recientes]


def fb_serie(valores, clave_bd=None):
    """Valores diarios de una métrica de página → {día: valor} (o {día: {bd: valor}} con desglose)."""
    out = {}
    for v in valores or []:
        dia = SOCIAL._dia(v["end_time"])
        if clave_bd:
            out.setdefault(dia, {})[str(v.get(clave_bd))] = v.get("value") or 0
        else:
            out[dia] = v.get("value") or 0
    return out


def organico_cuenta(cfg, hoy, cache, dias_antes=14, ahora_utc=None, social=None):
    ini = datetime.date.fromisoformat(cfg["inicio_organico"])
    desde = (ini - datetime.timedelta(days=dias_antes)).isoformat()
    hasta = min(ultimo_cerrado(ahora_utc), hoy)
    tok = _token()
    # IG, día por día con caché.
    guardados = cache.setdefault("ig_dia", {})
    for f in dias_ig_a_pedir(guardados, desde, hasta):
        v = ig_dia(f, tok)
        if v.get("vistas_org") or v.get("vistas_ads"):   # un día sin datos todavía no llegó
            guardados[f] = v
    # FB, serie entera en dos llamadas.
    ok, err, paginas = SOCIAL._token_paginas()
    if not ok:
        raise RuntimeError(f"tokens de página: {err}")
    ptok = (paginas.get(PAGE_ID) or {}).get("access_token")
    a = SOCIAL._ts(datetime.date.fromisoformat(desde))
    b = SOCIAL._ts(datetime.date.fromisoformat(hoy) + datetime.timedelta(days=1))
    pl = _get(f"{PAGE_ID}/insights", metric="page_media_view", period="day", breakdown="is_from_ads",
              since=a, until=b, access_token=ptok)
    fb_vistas = fb_serie(((pl.get("data") or [{}])[0]).get("values"), "is_from_ads")
    pl = _get(f"{PAGE_ID}/insights", metric="page_video_views_organic,page_video_views_paid", period="day",
              since=a, until=b, access_token=ptok)
    fb_video = {d["name"]: fb_serie(d.get("values")) for d in pl.get("data") or []}
    # Seguidores: altas pagadas/orgánicas, bajas, total y reacciones por tipo (una llamada).
    pl = _get(f"{PAGE_ID}/insights", metric="page_fan_adds_by_paid_non_paid_unique,page_daily_unfollows_unique,"
              "page_follows,page_actions_post_reactions_total", period="day", since=a, until=b, access_token=ptok)
    fb_seg = {d["name"]: fb_serie(d.get("values")) for d in pl.get("data") or []}
    altas = fb_seg.get("page_fan_adds_by_paid_non_paid_unique") or {}
    reac = fb_seg.get("page_actions_post_reactions_total") or {}

    dias = sorted(d for d in set(guardados) | set(fb_vistas) if desde <= d <= hasta)
    ig = {k: [guardados.get(d, {}).get(k) for d in dias] for k in sorted({k for v in guardados.values() for k in v})}
    fb = {"vistas_org": [fb_vistas.get(d, {}).get("0") for d in dias],
          "vistas_ads": [fb_vistas.get(d, {}).get("1") for d in dias],
          "video_org": [(fb_video.get("page_video_views_organic") or {}).get(d) for d in dias],
          "video_ads": [(fb_video.get("page_video_views_paid") or {}).get(d) for d in dias],
          "altas_pag": [(altas.get(d) or {}).get("paid") if isinstance(altas.get(d), dict) else None for d in dias],
          "altas_org": [(altas.get(d) or {}).get("unpaid") if isinstance(altas.get(d), dict) else None for d in dias],
          "bajas": [(fb_seg.get("page_daily_unfollows_unique") or {}).get(d) for d in dias],
          "seguidores": [(fb_seg.get("page_follows") or {}).get(d) for d in dias]}
    for tipo in sorted({k for v in reac.values() if isinstance(v, dict) for k in v}):
        fb[f"r_{tipo}"] = [(reac.get(d) or {}).get(tipo, 0) if isinstance(reac.get(d), dict) else None for d in dias]
    fb["r_pos"] = [None if not isinstance(reac.get(d), dict) else tono(reac[d])[0] for d in dias]
    fb["r_neg"] = [None if not isinstance(reac.get(d), dict) else tono(reac[d])[1] for d in dias]
    # Seguidores de IG: la foto diaria que guarda salud-marca (`ig_total`, sin corrimiento de día).
    datos = ((social or {}).get("datos") or {}).get("MX") or {}
    ig["seguidores"] = [(datos.get(d) or {}).get("ig_total") for d in dias]
    antes = (desde, (ini - datetime.timedelta(days=1)).isoformat())
    return {"dias": dias, "ig": ig, "fb": fb, "antes": antes, "despues": (cfg["inicio_organico"], hasta)}


def miniaturas(ids, imagenes, grandes=(), chica=240, grande=720):
    """`{id}.jpg` chica para todo y `{id}_g.jpg` grande para los anuncios (vista previa). Baja solo lo
    que falta y borra lo que ya no está. Devuelve los ids con miniatura."""
    os.makedirs(MINIATURAS, exist_ok=True)
    quedan = set(ids)
    for f in os.listdir(MINIATURAS):
        if f.endswith(".jpg") and f[:-4].removesuffix("_g") not in quedan:
            os.remove(os.path.join(MINIATURAS, f))
    con = set()
    for i in quedan:
        rutas = [(os.path.join(MINIATURAS, f"{i}.jpg"), chica)]
        if i in grandes:
            rutas.append((os.path.join(MINIATURAS, f"{i}_g.jpg"), grande))
        falta = any(not os.path.exists(r) or (lado > 100 and _chica(r)) for r, lado in rutas)
        if falta and imagenes.get(i):
            try:
                url = imagenes[i]() if callable(imagenes[i]) else imagenes[i]
                if not url:
                    raise RuntimeError("sin imagen")
                crudo = urlopen(url, timeout=30).read()
                for ruta, lado in rutas:
                    try:
                        from PIL import Image
                        im = Image.open(io.BytesIO(crudo)).convert("RGB")
                        im.thumbnail((lado, lado))
                        im.save(ruta, "JPEG", quality=80)
                    except ImportError:
                        open(ruta, "wb").write(crudo)
            except Exception as e:  # noqa: BLE001
                print(f"WARN miniatura {i}: {e}")
        if os.path.exists(rutas[0][0]):
            con.add(i)
    return con


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

    def _organico_cuenta():
        return organico_cuenta(cfg, hoy, cache, social=social)

    def _cuenta():
        if not social:
            raise RuntimeError("no se pudo leer salud-marca/social_cache.json")
        return cuenta(social, cfg["inicio_organico"], hoy)

    out = {"generated_at": ahora, "config": {k: cfg.get(k) for k in ("inicio_organico", "inicio_pagado", "patron", "prefijo_ads")}}
    for nombre, fn in (("pagado", _pagado), ("organico", _organico), ("organico_cuenta", _organico_cuenta), ("cuenta", _cuenta)):
        out[nombre], _ = _seccion(nombre, fn, cache, ahora)
        if out[nombre]["status"] == "ok":
            cache[nombre] = out[nombre]

    # Miniaturas de anuncios y posts (una carpeta; se borran las que ya no salen).
    ids = [{"id": i} for i in (out["pagado"].get("anuncios") or {})] + \
          [{"id": p["id"]} for p in (out["organico"].get("posts") or [])]
    grandes = set(out["pagado"].get("anuncios") or {})
    con = miniaturas([p["id"] for p in ids], imagenes, grandes) if ids else set()
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
    print(f"orgánico de la cuenta: {d['organico_cuenta']['status']} · {len(d['organico_cuenta'].get('dias') or [])} días")
    print(f"cuenta: {d['cuenta']['status']}")
