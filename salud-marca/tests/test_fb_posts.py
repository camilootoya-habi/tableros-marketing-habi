import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_fb_posts as F


def raw(i, fecha, tipo="added_video", reac=10, coment=2, shares=None):
    r = {"id": i, "created_time": f"{fecha}T15:00:00+0000", "status_type": tipo, "permalink_url": f"https://fb/{i}",
         "message": "Vende tu casa\notra línea", "full_picture": f"https://cdn/{i}.jpg",
         "reactions": {"summary": {"total_count": reac}}, "comments": {"summary": {"total_count": coment}}}
    if shares is not None:
        r["shares"] = {"count": shares}
    return r


def test_formato_por_tipo_de_publicacion():
    assert F.formato({"status_type": "added_video"}) == "video"
    assert F.formato({"status_type": "added_photos"}) == "foto"
    assert F.formato({"status_type": "mobile_status_update"}) == "texto"


def test_normalizar_toma_totales_y_compartidos_aunque_falten():
    p = F.normalizar(raw("a", "2026-09-01", shares=4))
    assert (p["reacciones"], p["comentarios"], p["compartidos"]) == (10, 2, 4)
    assert F.normalizar(raw("b", "2026-09-01"))["compartidos"] == 0, "sin shares = 0, no error"
    assert p["texto"] == "Vende tu casa"


def test_actualizar_pide_metricas_solo_de_lo_reciente(monkeypatch):
    monkeypatch.setattr(F, "listar", lambda pid, tok, paginas: [raw("nuevo", "2026-10-01"), raw("viejo", "2025-01-01")])
    pedidas = []
    monkeypatch.setattr(F, "metricas", lambda pid, tok: pedidas.append(pid) or {"vistas": 900})
    posts, imgs = F.actualizar({}, "page", "tok", hoy="2026-10-06")
    assert pedidas == ["nuevo"] and posts["nuevo"]["vistas"] == 900 and "vistas" not in posts["viejo"]
    assert imgs["viejo"] == "https://cdn/viejo.jpg" and "_img" not in posts["viejo"]


def test_mensual_y_top_usan_reacciones_mas_comentarios_mas_compartidos():
    posts = {"a": {"fecha": "2026-09-02", "formato": "video", "reacciones": 10, "comentarios": 2, "compartidos": 3},
             "b": {"fecha": "2026-09-20", "formato": "foto", "reacciones": 40, "comentarios": 0, "compartidos": 0}}
    assert F.mensual(posts)["2026-09"] == {"fbpub_video": 1, "fbint_video": 15, "fbpub_foto": 1, "fbint_foto": 40}
    assert [p["id"] for p in F.top(posts)] == ["b", "a"]
