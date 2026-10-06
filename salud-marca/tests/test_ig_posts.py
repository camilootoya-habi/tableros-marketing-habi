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
    monkeypatch.setattr(P, "con_pauta", lambda pid: pid == "nuevo")
    posts, imgs = P.actualizar({}, "ig", hoy="2026-10-06")
    assert posts["nuevo"]["pauta"] is True and "pauta" not in posts["viejo"], "solo lo reciente se verifica a diario"
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


def test_top_organicas_verifica_candidatos_y_salta_pautados_y_los_que_no_se_pudieron_verificar():
    posts = {"pautado": {"fecha": "2026-09-01", "likes": 900, "comentarios": 0},
             "falla": {"fecha": "2026-09-02", "likes": 800, "comentarios": 0},
             "org1": {"fecha": "2026-09-03", "likes": 700, "comentarios": 0, "pauta": False},
             "org2": {"fecha": "2026-09-04", "likes": 600, "comentarios": 0}}
    respuestas = {"pautado": True, "falla": None, "org2": False}
    llamadas = []
    verificar = lambda i: llamadas.append(i) or respuestas[i]
    top = P.top(posts, "2026-01-01", n=2, organicas=True, verificar=verificar)
    assert [p["id"] for p in top] == ["org1", "org2"]
    assert llamadas == ["pautado", "falla", "org2"], "org1 ya estaba verificado: no se vuelve a pedir"
    assert posts["pautado"]["pauta"] is True and "pauta" not in posts["falla"], "el resultado queda en el caché"


def test_top_historico_usa_likes_mas_comentarios_para_no_favorecer_lo_reciente():
    posts = {"viejo": {"fecha": "2022-01-01", "likes": 500, "comentarios": 50},
             "nuevo": {"fecha": "2026-09-01", "likes": 100, "comentarios": 0, "interacciones": 900}}
    assert [p["id"] for p in P.top(posts, criterio=P.likes_coment)] == ["viejo", "nuevo"]


def test_miniaturas_borra_las_que_ya_no_estan_en_el_top(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "MINIATURAS", str(tmp_path))
    (tmp_path / "viejo.jpg").write_bytes(b"x")
    (tmp_path / "sigue.jpg").write_bytes(b"x")
    con = P.miniaturas([[{"id": "sigue"}]], {})
    assert con == {"sigue"} and not (tmp_path / "viejo.jpg").exists()
