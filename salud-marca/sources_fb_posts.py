"""Publicaciones de las páginas de Facebook de las tres marcas.

Lo que da Meta (verificado el 6-oct-2026 con el token de AgenteCreativo, página de Tuhabi):
- La lista de posts trae toda la historia (Tuhabi: 808 desde jun-2021) con fecha, tipo (video o
  fotos), link, texto, imagen, reacciones, comentarios y compartidos. Reacciones + comentarios +
  compartidos es la métrica comparable en toda la historia.
- Por post: vistas (`post_media_view`), clics y vistas de video. El alcance por post ya no lo da
  (`post_total_media_view_unique` responde 0). Una llamada por post: solo los últimos 45 días a
  diario, y en el backfill los últimos 180.
- **No se puede saber si un post tuvo pauta**: `promotion_status` dice "inactive" o "ineligible"
  en todos (300 revisados), se haya pautado o no. La otra vía es recorrer los anuncios de las cuentas,
  que es lo que agotó la cuota de la cuenta de Tuhabi el 6-oct. Por eso el top de Facebook no tiene
  filtro de orgánicas.

Ojo: reacciones, comentarios y vistas incluyen lo que trae la pauta.
"""
import datetime
import os

import sources_brand_lift as BL
import sources_ig_posts as IGP

HERE = os.path.dirname(os.path.abspath(__file__))
MINIATURAS = os.path.join(HERE, "fb_miniaturas")
CAMPOS = ("id,created_time,status_type,permalink_url,message,full_picture,shares,"
          "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)")
METRICAS = {"post_media_view": "vistas", "post_clicks": "clics", "post_video_views": "vistas_video"}


def formato(raw):
    t = raw.get("status_type") or ""
    return "video" if "video" in t else "foto" if "photo" in t else "texto"


def _total(raw, campo):
    return ((raw.get(campo) or {}).get("summary") or {}).get("total_count") or 0


def normalizar(raw):
    return {
        "fecha": (raw.get("created_time") or "")[:10],
        "formato": formato(raw),
        "link": raw.get("permalink_url"),
        "texto": (raw.get("message") or "").strip().split("\n")[0][:140],
        "reacciones": _total(raw, "reactions"),
        "comentarios": _total(raw, "comments"),
        "compartidos": (raw.get("shares") or {}).get("count") or 0,
        "_img": raw.get("full_picture"),   # caduca: no se guarda
    }


def listar(page_id, page_token, paginas=1):
    """Los posts más recientes primero. `paginas=None` = toda la historia (backfill)."""
    out, after, n = [], None, 0
    while paginas is None or n < paginas:
        params = {"fields": CAMPOS, "limit": 100, "access_token": page_token}
        if after:
            params["after"] = after
        ok, pl = BL._get(f"{page_id}/posts", **params)
        if not ok:
            raise RuntimeError((pl.get("error") or {}).get("message"))
        out += pl.get("data") or []
        n += 1
        after = ((pl.get("paging") or {}).get("cursors") or {}).get("after")
        if not (pl.get("paging") or {}).get("next"):
            break
    return out


def metricas(post_id, page_token):
    ok, pl = BL._get(f"{post_id}/insights", metric=",".join(METRICAS), access_token=page_token)
    if not ok:
        return {}
    return {METRICAS[d["name"]]: (d.get("values") or [{}])[0].get("value")
            for d in pl.get("data") or [] if d.get("name") in METRICAS}


def actualizar(posts, page_id, page_token, paginas=1, dias_metricas=45, hoy=None):
    """Funde en `posts` lo que trae la API. → (posts, {id: url de imagen})."""
    hoy = hoy or datetime.date.today().isoformat()
    desde = (datetime.date.fromisoformat(hoy) - datetime.timedelta(days=dias_metricas)).isoformat()
    imagenes = {}
    for raw in listar(page_id, page_token, paginas):
        p = normalizar(raw)
        imagenes[raw["id"]] = p.pop("_img")
        if p["fecha"] >= desde:
            p.update(metricas(raw["id"], page_token))
        posts.setdefault(raw["id"], {}).update(p)
    return posts, imagenes


def url_imagen(post_id, page_token):
    """URL fresca de la imagen de un post viejo (las de la lista caducan)."""
    ok, pl = BL._get(post_id, fields="full_picture", access_token=page_token)
    return pl.get("full_picture") if ok else None


def interacciones(p):
    return p.get("reacciones", 0) + p.get("comentarios", 0) + p.get("compartidos", 0)


def mensual(posts):
    """{AAAA-MM: {fbpub_<formato>, fbint_<formato>}}: publicaciones y reacciones + comentarios +
    compartidos del mes, por formato."""
    out = {}
    for p in posts.values():
        m = out.setdefault(p["fecha"][:7], {})
        f = p["formato"]
        m[f"fbpub_{f}"] = m.get(f"fbpub_{f}", 0) + 1
        m[f"fbint_{f}"] = m.get(f"fbint_{f}", 0) + interacciones(p)
    return out


def top(posts, desde="", n=10):
    return IGP.top(posts, desde, n=n, criterio=interacciones)


def miniaturas(tops, imagenes):
    return IGP.miniaturas(tops, imagenes, carpeta=MINIATURAS)
