"""Publicaciones de Instagram de las tres marcas: cuántas, de qué formato y cómo rinden.

Lo que da Meta (verificado el 6-oct-2026 con el token de AgenteCreativo):
- La lista de publicaciones trae TODA la historia (Tuhabi desde 2021, Habi y Propiedades.com
  desde 2019) con formato, fecha, link, texto, likes y comentarios. Son ~27 llamadas para las tres
  marcas completas, así que likes + comentarios son la única métrica comparable en 5 años.
- Las métricas por publicación (vistas, alcance, guardados, compartidos) piden UNA llamada por
  post. Solo se piden para lo publicado desde ago-2025: antes de eso Meta devuelve vistas en 0.
- Las URLs de imagen caducan. Las miniaturas del top (180 días e histórico, con y sin pauta) se
  descargan chicas al repo (`ig_miniaturas/`); las que salen del top se borran.

Ojo: likes, comentarios y vistas incluyen lo que trae la pauta cuando un post se promociona.
"""
import datetime
import io
import os
from urllib.request import urlopen

import sources_brand_lift as BL

HERE = os.path.dirname(os.path.abspath(__file__))
MINIATURAS = os.path.join(HERE, "ig_miniaturas")
CAMPOS = ("id,media_product_type,media_type,timestamp,permalink,caption,like_count,"
          "comments_count,thumbnail_url,media_url")
INSIGHTS_DESDE = "2025-08-01"      # antes de esto las vistas por post vienen en 0
METRICAS = "views,reach,saved,shares,total_interactions"


def formato(raw):
    """Tres formatos para leer el contenido: video (Reels y los videos de feed de antes de que
    existieran los Reels), carrusel e imagen."""
    t = raw.get("media_type")
    return "video" if t == "VIDEO" else "carrusel" if t == "CAROUSEL_ALBUM" else "imagen"


def normalizar(raw):
    return {
        "fecha": (raw.get("timestamp") or "")[:10],
        "formato": formato(raw),
        "link": raw.get("permalink"),
        "texto": (raw.get("caption") or "").strip().split("\n")[0][:140],
        "likes": raw.get("like_count") or 0,
        "comentarios": raw.get("comments_count") or 0,
        "_img": raw.get("thumbnail_url") or raw.get("media_url"),   # caduca: no se guarda
    }


def _token():
    t = BL._tokens()
    if not t:
        raise RuntimeError("sin token de Meta")
    return t[0][1]


def listar(ig_id, paginas=1):
    """Las publicaciones más recientes primero. `paginas=None` = toda la historia (backfill)."""
    out, after, n = [], None, 0
    while paginas is None or n < paginas:
        params = {"fields": CAMPOS, "limit": 100, "access_token": _token()}
        if after:
            params["after"] = after
        ok, pl = BL._get(f"{ig_id}/media", **params)
        if not ok:
            raise RuntimeError((pl.get("error") or {}).get("message"))
        out += pl.get("data") or []
        n += 1
        after = ((pl.get("paging") or {}).get("cursors") or {}).get("after")
        if not (pl.get("paging") or {}).get("next"):
            break
    return out


def metricas(post_id):
    ok, pl = BL._get(f"{post_id}/insights", metric=METRICAS, access_token=_token())
    if not ok:
        return {}
    nombres = {"views": "vistas", "reach": "alcance", "saved": "guardados", "shares": "compartidos",
               "total_interactions": "interacciones"}
    return {nombres[d["name"]]: (d.get("values") or [{}])[0].get("value")
            for d in pl.get("data") or [] if d.get("name") in nombres}


# ── ¿Tuvo pauta? ─────────────────────────────────────────────────────────────
# Dos fuentes, verificadas el 6-oct-2026 sobre los últimos 60 posts de @tuhabimx (coinciden en los
# mismos 2 posts):
#  1. `boost_ads_list` del post: los anuncios que lo promocionan, sin importar desde qué cuenta se
#     lanzaron. Una llamada por post: se usa a diario para lo reciente y para verificar candidatos.
#  2. Los anuncios de las cuentas que ve el token cuyo creativo es un post de Instagram
#     (`effective_instagram_media_id`). Son ~16 mil anuncios (~150 llamadas): solo en el backfill.
# `pauta`: True = tuvo; False = verificado sin pauta; ausente = no verificado.
CUENTAS = ("act_205661715114408", "act_1719704135983664", "act_234510228146877",
           "act_770068953990542", "act_3159349764081647", "act_1746373153181888",
           "act_1102638265553679", "act_27374651732195975")


def con_pauta(post_id):
    """True/False según `boost_ads_list`; None si la API falló (no se adivina)."""
    ok, pl = BL._get(post_id, fields="boost_ads_list", access_token=_token())
    if not ok:
        return None
    return bool((pl.get("boost_ads_list") or {}).get("data"))


def media_en_anuncios(cuentas=CUENTAS):
    """Ids de publicaciones de Instagram usadas como creativo en algún anuncio. SOLO BACKFILL."""
    ids = set()
    for act in cuentas:
        after = None
        while True:
            params = {"fields": "creative{effective_instagram_media_id,source_instagram_media_id}",
                      "limit": 100, "access_token": _token()}
            if after:
                params["after"] = after
            ok, pl = BL._get(f"{act}/ads", **params)
            if not ok:
                print(f"WARN anuncios {act}: {(pl.get('error') or {}).get('message')}")
                break
            for a in pl.get("data") or []:
                cr = a.get("creative") or {}
                ids |= {cr[k] for k in ("effective_instagram_media_id", "source_instagram_media_id") if cr.get(k)}
            after = ((pl.get("paging") or {}).get("cursors") or {}).get("after")
            if not (pl.get("paging") or {}).get("next"):
                break
    return ids


def url_imagen(post_id):
    """URL fresca de la imagen de un post viejo (las de la lista caducan y el cron solo relee
    las 100 más recientes)."""
    ok, pl = BL._get(post_id, fields="thumbnail_url,media_url", access_token=_token())
    return (pl.get("thumbnail_url") or pl.get("media_url")) if ok else None


def actualizar(posts, ig_id, paginas=1, metricas_desde=None, hoy=None):
    """Funde en `posts` ({id: post}) lo que trae la API. El cron pide 1 página (las 100 más
    recientes) y re-pide métricas de lo publicado en los últimos 45 días, que es cuando todavía se
    mueven. El backfill pide toda la historia y métricas desde `INSIGHTS_DESDE`.
    → (posts, {id: url de imagen}) — las URLs solo sirven unas horas, para bajar miniaturas ya."""
    hoy = hoy or datetime.date.today().isoformat()
    desde = metricas_desde or (datetime.date.fromisoformat(hoy) - datetime.timedelta(days=45)).isoformat()
    desde = max(desde, INSIGHTS_DESDE)
    imagenes = {}
    for raw in listar(ig_id, paginas):
        p = normalizar(raw)
        imagenes[raw["id"]] = p.pop("_img")
        if p["fecha"] >= desde:
            p.update(metricas(raw["id"]))
            # Lo reciente se re-verifica: un post se puede pautar días después de publicarlo.
            if posts.get(raw["id"], {}).get("pauta") is not True:
                v = con_pauta(raw["id"])
                if v is not None:
                    p["pauta"] = v
        posts.setdefault(raw["id"], {}).update(p)
    return posts, imagenes


def mensual(posts):
    """{AAAA-MM: {pub_video, pub_carrusel, pub_imagen, li_video, …, vistas_post, n_vistas}}
    `li_*` = likes + comentarios sumados (la métrica comparable en toda la historia)."""
    out = {}
    for p in posts.values():
        m = out.setdefault(p["fecha"][:7], {})
        f = p["formato"]
        m[f"pub_{f}"] = m.get(f"pub_{f}", 0) + 1
        m[f"li_{f}"] = m.get(f"li_{f}", 0) + p.get("likes", 0) + p.get("comentarios", 0)
        if p.get("vistas"):
            m[f"vistas_{f}"] = m.get(f"vistas_{f}", 0) + p["vistas"]
            m[f"nv_{f}"] = m.get(f"nv_{f}", 0) + 1
    return out


def puntaje(p):
    """Para ordenar el top: interacciones de Meta (incluye guardados y compartidos) si las hay;
    si no, likes + comentarios."""
    return p.get("interacciones") if p.get("interacciones") is not None else p.get("likes", 0) + p.get("comentarios", 0)


def likes_coment(p):
    return p.get("likes", 0) + p.get("comentarios", 0)


def top(posts, desde="", n=5, organicas=False, criterio=puntaje, verificar=None):
    """Las `n` publicaciones con mejor `criterio` desde la fecha `desde` (AAAA-MM-DD).
    Con `organicas=True` deja fuera las que tuvieron pauta. Un candidato sin verificar se verifica
    con `verificar(id)` (normalmente `con_pauta`) y el resultado queda guardado en `posts`; si la
    verificación falla, el candidato se salta: mejor perder una orgánica que colar una pautada."""
    candidatos = sorted(((i, p) for i, p in posts.items() if p["fecha"] >= desde),
                        key=lambda x: criterio(x[1]), reverse=True)
    out = []
    for i, p in candidatos:
        if organicas:
            if "pauta" not in p and verificar:
                v = verificar(i)
                if v is not None:
                    p["pauta"] = v
            if p.get("pauta") is not False:
                continue
        out.append(dict(p, id=i))
        if len(out) == n:
            break
    return out


def miniaturas(tops, imagenes, lado=240, carpeta=None):
    """Baja chica la miniatura de cada post del top (si no está ya) y borra las que ya no salen.
    Sin Pillow guarda la imagen tal cual. Devuelve los ids que tienen miniatura.
    `carpeta`: cada red tiene la suya, porque la limpieza borra todo lo que no está en SU top."""
    carpeta = carpeta or MINIATURAS
    os.makedirs(carpeta, exist_ok=True)
    quedan = {p["id"] for t in tops for p in t}
    for f in os.listdir(carpeta):
        if f.endswith(".jpg") and f[:-4] not in quedan:
            os.remove(os.path.join(carpeta, f))
    con = set()
    for pid in quedan:
        ruta = os.path.join(carpeta, f"{pid}.jpg")
        if not os.path.exists(ruta) and imagenes.get(pid):
            try:
                crudo = urlopen(imagenes[pid], timeout=30).read()
                try:
                    from PIL import Image
                    im = Image.open(io.BytesIO(crudo)).convert("RGB")
                    im.thumbnail((lado, lado))
                    im.save(ruta, "JPEG", quality=78)
                except ImportError:
                    open(ruta, "wb").write(crudo)
            except Exception as e:
                print(f"WARN miniatura {pid}: {e}")
        if os.path.exists(ruta):
            con.add(pid)
    return con
