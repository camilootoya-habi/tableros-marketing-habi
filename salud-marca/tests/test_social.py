import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import build
import sources_social as S


def test_el_dia_del_dato_es_el_anterior_al_end_time():
    assert S._dia("2026-10-06T07:00:00+0000") == "2026-10-05"
    assert S._dia("2026-01-01T08:00:00+0000") == "2025-12-31"


def test_merge_nunca_borra_y_pisa_campo_por_campo():
    cache = {"datos": {"MX": {"2026-10-01": {"fb_total": 10, "ig_total": 5}}}, "last_refresh": "x"}
    fresh = {"MX": {"2026-10-01": {"fb_total": 11}, "2026-10-02": {"fb_total": 12}}}
    cache["posts"] = {"MX": {"p1": {"likes": 3}}}
    m = S.merge(cache, fresh)
    assert m["posts"] == {"MX": {"p1": {"likes": 3}}}, "merge conserva las publicaciones"
    assert m["datos"]["MX"]["2026-10-01"] == {"fb_total": 11, "ig_total": 5}
    assert m["datos"]["MX"]["2026-10-02"] == {"fb_total": 12}
    assert cache["datos"]["MX"]["2026-10-01"]["fb_total"] == 10, "no muta el caché de entrada"


def test_fb_insights_separa_diccionarios_y_toma_el_alcance_de_28_dias(monkeypatch):
    def fake_get(path, token, **p):
        if p["metric"] == "page_total_media_view_unique":
            return True, {"data": [{"values": [{"end_time": "2026-09-30T07:00:00+0000", "value": 8000}]}]}
        return True, {"data": [
            {"name": "page_media_view", "values": [{"end_time": "2026-09-30T07:00:00+0000", "value": 1000}]},
            {"name": "page_fan_adds_by_paid_non_paid_unique",
             "values": [{"end_time": "2026-09-30T07:00:00+0000", "value": {"paid": 3, "unpaid": 2, "total": 5}}]},
            {"name": "page_actions_post_reactions_total",
             "values": [{"end_time": "2026-09-30T07:00:00+0000", "value": {"like": 40, "anger": 1}}]}]}
    monkeypatch.setattr(S, "_get", fake_get)
    d = S._fb_insights("page", "tok", 0, 1)["2026-09-29"]
    assert d == {"fb_vistas": 1000, "fb_altas_pag": 3, "fb_altas_org": 2, "fb_r_like": 40, "fb_r_anger": 1,
                 "fb_alcance28": 8000}


def test_mensual_suma_las_metricas_de_facebook_y_toma_el_alcance_del_cierre():
    filas = [{"date": "2026-09-01", "fb_vistas": 10, "fb_altas_pag": 1, "fb_r_like": 4, "fb_alcance28": 500},
             {"date": "2026-09-30", "fb_vistas": 20, "fb_altas_pag": 2, "fb_r_like": 6, "fb_alcance28": 900}]
    m = S.mensual(filas)[0]
    assert (m["fb_vistas"], m["fb_altas_pag"], m["fb_r_like"], m["fb_alcance28"]) == (30, 3, 10, 900)


def test_ig_dia_pide_una_ventana_de_un_dia_y_descarta_dias_sin_vistas(monkeypatch):
    ventanas = []

    def fake_get(path, token, **p):
        ventanas.append(p["until"] - p["since"])
        if p["metric"] == "follows_and_unfollows":
            return True, {"data": [{"total_value": {"breakdowns": [{"results": [
                {"dimension_values": ["FOLLOWER"], "value": 20}, {"dimension_values": ["NON_FOLLOWER"], "value": 7}]}]}}]}
        return True, {"data": [{"name": "views", "total_value": {"value": vistas}},
                               {"name": "total_interactions", "total_value": {"value": 90}}]}
    monkeypatch.setattr(S, "_get", fake_get)
    vistas = 3000
    assert S._ig_dia("ig", "tok", "2026-10-03") == {"ig_altas_d": 20, "ig_bajas_d": 7, "ig_vistas_d": 3000, "ig_inter_d": 90}
    assert set(ventanas) == {S.DIA}
    vistas = 0
    assert S._ig_dia("ig", "tok", "2026-10-05") == {"ig_altas_d": 20, "ig_bajas_d": 7}


def test_mensual_borra_meses_de_facebook_que_la_api_da_en_cero():
    # 2023: Meta da 0 en vistas y altas pagadas/orgánicas aunque hubo 300 altas → no es dato.
    filas = [{"date": "2023-05-10", "fb_altas": 300, "fb_bajas": 5, "fb_vistas": 0, "fb_altas_pag": 0,
              "fb_altas_org": 0, "fb_r_like": 0},
             {"date": "2026-09-10", "fb_altas": 30, "fb_bajas": 1, "fb_vistas": 900, "fb_altas_pag": 0,
              "fb_altas_org": 12, "fb_r_like": 4}]
    viejo, nuevo = S.mensual(filas)
    assert not any(k in viejo for k in ("fb_vistas", "fb_altas_pag", "fb_altas_org", "fb_r_like"))
    assert viejo["fb_altas"] == 300, "las altas totales sí son reales"
    assert nuevo["fb_altas_pag"] == 0 and nuevo["fb_altas_org"] == 12, "un cero dentro de un grupo con dato sí cuenta"


def test_ig_no_guarda_ceros_recientes_que_todavia_no_llegan(monkeypatch):
    valores = [{"end_time": "2026-10-01T07:00:00+0000", "value": 0},
               {"end_time": "2026-10-03T07:00:00+0000", "value": 40},
               {"end_time": "2026-10-05T07:00:00+0000", "value": 0}]
    monkeypatch.setattr(S, "_get", lambda *a, **k: (True, {"data": [{"values": valores}]}))
    dias = S._ig_nuevos("ig", "tok", 0, 1, hoy="2026-10-05")
    # 30-sep = 0 viejo (real) se guarda; 4-oct = 0 reciente (atraso de IG) no.
    assert dias == {"2026-09-30": {"ig_nuevos": 0}, "2026-10-02": {"ig_nuevos": 40}}


def test_series_descarta_el_total_congelado_y_lo_reconstruye_con_altas_y_bajas():
    datos = {"MX": {
        "2024-10-01": {"fb_total": 35831, "fb_altas": 5, "fb_bajas": 1},   # congelado: se descarta
        "2024-10-02": {"fb_total": 35831, "fb_altas": 4, "fb_bajas": 0},
        "2024-10-03": {"fb_total": 35831, "fb_altas": 3, "fb_bajas": 2},
        "2024-10-04": {"fb_total": 100, "fb_altas": 7, "fb_bajas": 1},     # primer total real
    }}
    f = S.series(datos, "MX")
    assert [r.get("fb_total") for r in f] == [None, None, None, 100]
    # 3-oct = 100 − 7 + 1 = 94 · 2-oct = 94 − 3 + 2 = 93 · 1-oct = 93 − 4 + 0 = 89
    assert [r.get("fb_total_est") for r in f] == [89, 93, 94, None]


def test_mensual_toma_el_cierre_del_total_y_suma_altas_bajas_y_nuevos():
    filas = [{"date": "2026-09-29", "fb_total": 10, "fb_altas": 2, "fb_bajas": 1, "ig_nuevos": 4},
             {"date": "2026-09-30", "fb_total": 11, "fb_altas": 3, "fb_bajas": 0, "ig_total": 50},
             {"date": "2026-10-01", "fb_total": 12, "fb_altas": 1, "fb_bajas": 0}]
    m = S.mensual(filas)
    assert m[0] == {"month": "2026-09", "fb_total": 11, "ig_total": 50, "fb_altas": 5, "fb_bajas": 1,
                    "ig_nuevos": 4, "dias_fb": 2, "dias_ig": 1}
    assert m[1]["month"] == "2026-10" and m[1]["fb_total"] == 12 and m[1]["dias_fb"] == 1


def test_ig_mes_suma_las_dos_mitades_y_descarta_meses_sin_datos(monkeypatch):
    llamadas = []

    def fake_get(path, token, **p):
        llamadas.append((p["since"], p["until"]))
        if p["metric"] == "follows_and_unfollows":
            return True, {"data": [{"total_value": {"breakdowns": [{"results": [
                {"dimension_values": ["FOLLOWER"], "value": 10}, {"dimension_values": ["NON_FOLLOWER"], "value": 3}]}]}}]}
        return True, {"data": [{"name": "views", "total_value": {"value": 100}},
                               {"name": "total_interactions", "total_value": {"value": 5}}]}
    monkeypatch.setattr(S, "_get", fake_get)
    v = S._ig_mes("ig", "tok", datetime.date(2026, 8, 1), ahora=10 ** 10)
    assert v == {"ig_altas": 20, "ig_bajas": 6, "ig_vistas": 200, "ig_interacciones": 10}
    assert all(b - a <= 30 * S.DIA for a, b in llamadas), "ninguna ventana pasa de 30 días"

    # Mes viejo: la API devuelve vistas en 0 e interacciones negativas → no hay dato, no un cero.
    monkeypatch.setattr(S, "_get", lambda path, token, **p: (True, {"data": [
        {"name": "views", "total_value": {"value": 0}}, {"name": "total_interactions", "total_value": {"value": -5}}]}))
    assert S._ig_mes("ig", "tok", datetime.date(2025, 4, 1), ahora=10 ** 10) == {}


def test_ig_mes_sin_altas_en_una_mitad_no_guarda_altas_ni_bajas(monkeypatch):
    # La historia empieza a mitad de mes: la primera mitad no trae follows. Sería un mes "flojo"
    # falso, así que se descartan altas y bajas (las vistas sí cuentan).
    def fake_get(path, token, **p):
        if p["metric"] == "follows_and_unfollows":
            con = p["since"] >= S._ts(datetime.date(2025, 9, 16))
            res = [{"dimension_values": ["FOLLOWER"], "value": 13}] if con else []
            return True, {"data": [{"total_value": {"breakdowns": [{"results": res}]}}]}
        return True, {"data": [{"name": "views", "total_value": {"value": 100}},
                               {"name": "total_interactions", "total_value": {"value": 5}}]}
    monkeypatch.setattr(S, "_get", fake_get)
    v = S._ig_mes("ig", "tok", datetime.date(2025, 9, 1), ahora=10 ** 10)
    assert "ig_altas" not in v and v["ig_vistas"] == 200


def test_ig_mes_guarda_el_alcance_de_seguidores_y_no_seguidores(monkeypatch):
    def fake_get(path, token, **p):
        if p["metric"] == "reach":
            return True, {"data": [{"total_value": {"breakdowns": [{"results": [
                {"dimension_values": ["FOLLOWER"], "value": 120}, {"dimension_values": ["NON_FOLLOWER"], "value": 9000}]}]}}]}
        return True, {"data": []}
    monkeypatch.setattr(S, "_get", fake_get)
    v = S._ig_mes("ig", "tok", datetime.date(2026, 9, 1), ahora=10 ** 10)
    assert v == {"ig_alc_seg": 120, "ig_alc_noseg": 9000}


def test_save_cache_conserva_publicaciones_y_demografia_si_no_se_pasan():
    S.save_cache({}, None, {}, {"MX": {"p": {}}}, {"MX": {"2026-10": {"edad": {"25-34": 5}}}})
    S.save_cache({"MX": {}}, "t", {})
    c = S.load_cache()
    assert c["posts"] == {"MX": {"p": {}}} and c["ig_demo"]["MX"]["2026-10"]["edad"] == {"25-34": 5}


def test_mensual_reconstruye_el_total_de_instagram_hacia_atras():
    filas = [{"date": "2026-10-05", "ig_total": 1000}]
    ig_mes = {"2026-08": {"ig_altas": 50, "ig_bajas": 10},
              "2026-09": {"ig_altas": 70, "ig_bajas": 20},
              "2026-10": {"ig_altas": 30, "ig_bajas": 5}}
    m = {r["month"]: r for r in S.mensual(filas, ig_mes)}
    assert m["2026-10"]["ig_total"] == 1000
    assert m["2026-09"]["ig_total_est"] == 975        # 1000 − 30 + 5
    assert m["2026-08"]["ig_total_est"] == 925        # 975 − 70 + 20
    assert "ig_total_est" not in m["2026-10"]


def test_mensual_no_reconstruye_meses_que_ya_tienen_total_medido():
    filas = [{"date": "2026-10-31", "ig_total": 1000}, {"date": "2026-11-30", "ig_total": 1100}]
    ig_mes = {"2026-09": {"ig_altas": 10, "ig_bajas": 0}, "2026-10": {"ig_altas": 30, "ig_bajas": 5},
              "2026-11": {"ig_altas": 120, "ig_bajas": 20}}
    m = {r["month"]: r for r in S.mensual(filas, ig_mes)}
    assert "ig_total_est" not in m["2026-10"] and "ig_total_est" not in m["2026-11"]
    assert m["2026-09"]["ig_total_est"] == 975, "parte del primer mes medido (oct), no del último"


def _fetch_ok(hoy):
    return True, {c: {"2026-10-04": {"fb_total": 100, "ig_total": 50}} for c in S.MARCAS}, {}


def test_seguidores_ok_guarda_cache_y_publica_las_tres_marcas(monkeypatch):
    monkeypatch.setattr(S, "fetch", _fetch_ok)
    out = build.collect_seguidores("2026-10-05T13:00:00Z")
    assert set(out) == {"MX", "CO", "PCOM"}
    assert all(m["status"] == "ok" and m["series"][0]["fb_total"] == 100 for m in out.values())
    assert S.load_cache()["last_refresh"] == "2026-10-05T13:00:00Z"


def test_seguidores_fallo_con_cache_es_stale_con_fecha_del_ultimo_exito(monkeypatch):
    S.save_cache({"MX": {"2026-10-01": {"fb_total": 9}}}, "2026-10-02T13:00:00Z")
    monkeypatch.setattr(S, "fetch", lambda hoy: (False, {}, {"_": "token inválido"}))
    out = build.collect_seguidores("2026-10-05T13:00:00Z")
    assert out["MX"]["status"] == "stale" and out["MX"]["last_updated"] == "2026-10-02T13:00:00Z"
    assert out["CO"]["status"] == "error" and "token inválido" in out["CO"]["reason"]


def test_seguidores_falla_una_marca_las_otras_siguen(monkeypatch):
    def fetch(hoy):
        ok, datos, _ = _fetch_ok(hoy)
        datos.pop("PCOM")
        return ok, datos, {"PCOM": "el token no ve la página"}
    monkeypatch.setattr(S, "fetch", fetch)
    out = build.collect_seguidores("2026-10-05T13:00:00Z")
    assert out["MX"]["status"] == "ok" and out["CO"]["status"] == "ok"
    assert out["PCOM"]["status"] == "error" and "no ve la página" in out["PCOM"]["reason"]
