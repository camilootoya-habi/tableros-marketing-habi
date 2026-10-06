import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_ig_posts as P


def raw(i, fecha, tipo="VIDEO", likes=10, coments=2):
    return {"id": i, "timestamp": f"{fecha}T15:00:00+0000", "media_type": tipo, "permalink": f"https://ig/{i}",
            "caption": "Vende tu casa\nsegunda línea", "like_count": likes, "comments_count": coments,
            "thumbnail_url": f"https://cdn/{i}.jpg"}


def test_formato_agrupa_reels_y_videos_de_feed_como_video():
    assert P.formato({"media_type": "VIDEO"}) == "video"
    assert P.formato({"media_type": "CAROUSEL_ALBUM"}) == "carrusel"
    assert P.formato({"media_type": "IMAGE"}) == "imagen"


def test_actualizar_pide_metricas_solo_de_lo_reciente(monkeypatch):
    monkeypatch.setattr(P, "listar", lambda ig, paginas: [raw("nuevo", "2026-10-01"), raw("viejo", "2024-05-01")])
    pedidas = []
    monkeypatch.setattr(P, "metricas", lambda pid: pedidas.append(pid) or {"vistas": 500, "interacciones": 40})
    posts, imgs = P.actualizar({}, "ig", hoy="2026-10-06")
    assert pedidas == ["nuevo"]
    assert posts["nuevo"]["vistas"] == 500 and "vistas" not in posts["viejo"]
    assert posts["nuevo"]["texto"] == "Vende tu casa", "solo la primera línea del texto"
    assert imgs["nuevo"] == "https://cdn/nuevo.jpg" and "_img" not in posts["nuevo"], "la URL caduca: no se guarda"


def test_mensual_cuenta_por_formato_y_suma_likes_mas_comentarios():
    posts = {"a": {"fecha": "2026-09-02", "formato": "video", "likes": 10, "comentarios": 2, "vistas": 100},
             "b": {"fecha": "2026-09-20", "formato": "video", "likes": 5, "comentarios": 0},
             "c": {"fecha": "2026-09-21", "formato": "carrusel", "likes": 7, "comentarios": 1}}
    m = P.mensual(posts)["2026-09"]
    assert m == {"pub_video": 2, "li_video": 17, "vistas_video": 100, "nv_video": 1,
                 "pub_carrusel": 1, "li_carrusel": 8}


def test_top_ordena_por_interacciones_de_meta_y_si_no_hay_por_likes_mas_comentarios():
    posts = {"a": {"fecha": "2026-09-02", "likes": 100, "comentarios": 0},
             "b": {"fecha": "2026-09-03", "likes": 5, "comentarios": 0, "interacciones": 300},
             "c": {"fecha": "2026-08-30", "likes": 999, "comentarios": 0}}
    assert [p["id"] for p in P.top(posts, "2026-09")] == ["b", "a"]


def test_miniaturas_borra_las_que_ya_no_estan_en_el_top(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "MINIATURAS", str(tmp_path))
    (tmp_path / "viejo.jpg").write_bytes(b"x")
    (tmp_path / "sigue.jpg").write_bytes(b"x")
    con = P.miniaturas([[{"id": "sigue"}]], {})
    assert con == {"sigue"} and not (tmp_path / "viejo.jpg").exists()
