"""Publicaciones de Instagram de las tres marcas: cuántas, de qué formato y cómo rinden.

Lo que da Meta (verificado el 6-oct-2026 con el token de AgenteCreativo):
- La lista de publicaciones trae TODA la historia (Tuhabi desde 2021, Habi y Propiedades.com
  desde 2019) con formato, fecha, link, texto, likes y comentarios. Son ~27 llamadas para las tres
  marcas completas, así que likes + comentarios son la única métrica comparable en 5 años.
- Las métricas por publicación (vistas, alcance, guardados, compartidos) piden UNA llamada por
  post. Solo se piden para lo publicado desde ago-2025: antes de eso Meta devuelve vistas en 0.
- Las URLs de imagen caducan. Las miniaturas del top 5 se descargan chicas al repo
  (`ig_miniaturas/`) y solo para los meses que el tablero muestra; las demás se borran.

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


def top(posts, mes, n=5):
    del_mes = [dict(p, id=i) for i, p in posts.items() if p["fecha"].startswith(mes)]
    return sorted(del_mes, key=puntaje, reverse=True)[:n]


def miniaturas(tops, imagenes, lado=240):
    """Baja chica la miniatura de cada post del top (si no está ya) y borra las que ya no salen.
    Sin Pillow guarda la imagen tal cual. Devuelve los ids que tienen miniatura."""
    os.makedirs(MINIATURAS, exist_ok=True)
    quedan = {p["id"] for t in tops for p in t}
    for f in os.listdir(MINIATURAS):
        if f.endswith(".jpg") and f[:-4] not in quedan:
            os.remove(os.path.join(MINIATURAS, f))
    con = set()
    for pid in quedan:
        ruta = os.path.join(MINIATURAS, f"{pid}.jpg")
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
