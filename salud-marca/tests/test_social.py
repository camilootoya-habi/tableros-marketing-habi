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
    m = S.merge(cache, fresh)
    assert m["datos"]["MX"]["2026-10-01"] == {"fb_total": 11, "ig_total": 5}
    assert m["datos"]["MX"]["2026-10-02"] == {"fb_total": 12}
    assert cache["datos"]["MX"]["2026-10-01"]["fb_total"] == 10, "no muta el caché de entrada"


def test_ig_no_guarda_ceros_recientes_que_todavia_no_llegan(monkeypatch):
    valores = [{"end_time": "2026-10-01T07:00:00+0000", "value": 0},
               {"end_time": "2026-10-03T07:00:00+0000", "value": 40},
               {"end_time": "2026-10-05T07:00:00+0000", "value": 0}]
    monkeypatch.setattr(S, "_get", lambda *a, **k: (True, {"data": [{"values": valores}]}))
    dias = S._ig_nuevos("ig", "tok", 0, 1, hoy="2026-10-05")
    # 30-sep = 0 viejo (real) se guarda; 4-oct = 0 reciente (atraso de IG) no.
    assert dias == {"2026-09-30": {"ig_nuevos": 0}, "2026-10-02": {"ig_nuevos": 40}}


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
