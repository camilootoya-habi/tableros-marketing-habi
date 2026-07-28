import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import contract
import build


def test_un_driver_que_falla_no_tumba_a_los_demas(monkeypatch):
    monkeypatch.setattr(build, "collect_exit_poll", lambda: (_ for _ in ()).throw(RuntimeError("bq caído")))
    monkeypatch.setattr(build, "collect_traffic", lambda: [{"month": "2026-07", "plaza": "MTY", "users": 1, "spend": None, "cpv": None}])
    monkeypatch.setattr(build, "collect_brand_lift", lambda c, now: contract.metric("ok", source="api", series=[]))
    d = build.collect(now="2026-07-27T18:00:00Z")
    assert d["metrics"]["exit_poll"]["MX"]["status"] == "error"
    assert "bq caído" in d["metrics"]["exit_poll"]["MX"]["reason"]
    assert d["metrics"]["traffic"]["MX"]["status"] == "ok"


def test_co_declara_not_available_en_trafico_y_exit_poll(monkeypatch):
    monkeypatch.setattr(build, "collect_exit_poll", lambda: [])
    monkeypatch.setattr(build, "collect_traffic", lambda: [])
    monkeypatch.setattr(build, "collect_brand_lift", lambda c, now: contract.metric("ok", source="api", series=[]))
    d = build.collect(now="2026-07-27T18:00:00Z")
    for m in ("traffic", "exit_poll"):
        assert d["metrics"][m]["CO"]["status"] == "not_available"
        assert d["metrics"][m]["CO"]["reason"]
    assert "CO" in d["metrics"]["brand_lift"]


def test_brand_lift_una_excepcion_inesperada_no_tumba_los_demas(monkeypatch):
    # aisla el tercer driver igual que los otros dos: una excepción no manejada dentro de
    # collect_brand_lift (ej. caché corrupto) se convierte en status=error, sin tumbar traffic
    # ni exit_poll.
    monkeypatch.setattr(build, "collect_exit_poll", lambda: [])
    monkeypatch.setattr(build, "collect_traffic",
                         lambda: [{"month": "2026-07", "plaza": "MTY", "users": 1, "spend": None, "cpv": None}])

    def _boom(country, now):
        raise RuntimeError(f"cache corrupto {country}")
    monkeypatch.setattr(build, "collect_brand_lift", _boom)
    d = build.collect(now="2026-07-27T18:00:00Z")
    assert d["metrics"]["brand_lift"]["MX"]["status"] == "error"
    assert "cache corrupto MX" in d["metrics"]["brand_lift"]["MX"]["reason"]
    assert d["metrics"]["traffic"]["MX"]["status"] == "ok"


# --- collect_brand_lift() en sí: defecto 1 (timestamp honesto) y defecto 2 (persistencia). ---

CACHED_MX = {"country": "MX", "month": "2026-01", "question": None, "experiment_id": "1",
             "exposed": 0.10, "responders_test": 500}
FRESH_MX = {"country": "MX", "month": "2026-02", "question": None, "experiment_id": "2",
            "exposed": 0.20, "responders_test": 500}


def test_brand_lift_refresco_exitoso_es_ok_source_api_y_last_updated_now(monkeypatch):
    monkeypatch.setattr(build.BL, "load_cache", lambda: [CACHED_MX])
    monkeypatch.setattr(build.BL, "load_last_refresh", lambda: {})
    monkeypatch.setattr(build.BL, "fetch", lambda country: (True, [FRESH_MX]))
    monkeypatch.setattr(build.BL, "load_questions", lambda: {"1": "ad_recall", "2": "toma"})
    saved = {}
    monkeypatch.setattr(build.BL, "save_cache", lambda rows, lr: saved.update(rows=rows, last_refresh=lr))

    m = build.collect_brand_lift("MX", now="2026-07-27T18:00:00Z")

    assert m["status"] == "ok"
    assert m["source"] == "api"
    assert m["last_updated"] == "2026-07-27T18:00:00Z"
    assert {r["experiment_id"] for r in m["series"]} == {"1", "2"}
    # defecto 2: el éxito se persiste, fusionado, y el timestamp de éxito queda anotado
    assert {r["experiment_id"] for r in saved["rows"]} == {"1", "2"}
    assert saved["last_refresh"]["MX"] == "2026-07-27T18:00:00Z"


def test_brand_lift_refresco_fallido_con_cache_es_stale_con_source_cache_y_last_updated_del_ultimo_exito(monkeypatch):
    monkeypatch.setattr(build.BL, "load_cache", lambda: [CACHED_MX])
    monkeypatch.setattr(build.BL, "load_last_refresh", lambda: {"MX": "2026-07-10T09:00:00Z"})
    monkeypatch.setattr(build.BL, "fetch", lambda country: (False, []))
    monkeypatch.setattr(build.BL, "load_questions", lambda: {"1": "ad_recall"})
    monkeypatch.setattr(build.BL, "save_cache",
                         lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no debe escribir en un refresco fallido")))

    m = build.collect_brand_lift("MX", now="2026-07-27T18:00:00Z")

    assert m["status"] == "stale"
    assert m["source"] == "cache"
    # defecto 1: last_updated es el último éxito real, NO `now`
    assert m["last_updated"] == "2026-07-10T09:00:00Z"
    assert m["last_updated"] != "2026-07-27T18:00:00Z"
    assert len(m["series"]) == 1 and m["series"][0]["experiment_id"] == "1"


def test_brand_lift_refresco_fallido_sin_cache_es_error_con_razon(monkeypatch):
    monkeypatch.setattr(build.BL, "load_cache", lambda: [])
    monkeypatch.setattr(build.BL, "load_last_refresh", lambda: {})
    monkeypatch.setattr(build.BL, "fetch", lambda country: (False, []))

    m = build.collect_brand_lift("CO", now="2026-07-27T18:00:00Z")

    assert m["status"] == "error"
    assert m["reason"]
    assert "series" not in m


def test_brand_lift_refresco_exitoso_nunca_encoge_el_cache_persistido(monkeypatch):
    # la página de hoy trae menos estudios de los que ya había cacheados (p.ej. uno viejo
    # salió del top-10) — el archivo que se persiste debe conservar los 3, no truncar a 1.
    cached = [
        CACHED_MX,
        {"country": "MX", "month": "2026-02", "question": None, "experiment_id": "2", "exposed": 0.2},
        {"country": "MX", "month": "2026-03", "question": None, "experiment_id": "3", "exposed": 0.3},
    ]
    monkeypatch.setattr(build.BL, "load_cache", lambda: cached)
    monkeypatch.setattr(build.BL, "load_last_refresh", lambda: {})
    monkeypatch.setattr(build.BL, "fetch", lambda country: (True, [dict(CACHED_MX, exposed=0.11)]))
    monkeypatch.setattr(build.BL, "load_questions", lambda: {})
    saved = {}
    monkeypatch.setattr(build.BL, "save_cache", lambda rows, lr: saved.update(rows=rows, last_refresh=lr))

    build.collect_brand_lift("MX", now="2026-07-27T18:00:00Z")

    assert len(saved["rows"]) == 3
    assert {r["experiment_id"] for r in saved["rows"]} == {"1", "2", "3"}


def test_brand_lift_refresco_exitoso_de_mx_no_borra_las_filas_de_co_del_archivo(monkeypatch):
    # merge/save operan sobre el caché COMPLETO (ambos países), no solo el del país que se
    # está refrescando — si se filtrara por país antes de guardar, un refresco exitoso de MX
    # destruiría todo el histórico de CO en el mismo archivo.
    cached_co = {"country": "CO", "month": "2026-01", "question": None, "experiment_id": "99",
                 "exposed": 0.5}
    monkeypatch.setattr(build.BL, "load_cache", lambda: [CACHED_MX, cached_co])
    monkeypatch.setattr(build.BL, "load_last_refresh", lambda: {})
    monkeypatch.setattr(build.BL, "fetch", lambda country: (True, [FRESH_MX]))
    monkeypatch.setattr(build.BL, "load_questions", lambda: {})
    saved = {}
    monkeypatch.setattr(build.BL, "save_cache", lambda rows, lr: saved.update(rows=rows, last_refresh=lr))

    build.collect_brand_lift("MX", now="2026-07-27T18:00:00Z")

    assert any(r["country"] == "CO" and r["experiment_id"] == "99" for r in saved["rows"])
    assert len(saved["rows"]) == 3


def test_pais_con_estudios_pero_sin_preguntas_mapeadas_es_not_available(monkeypatch):
    """CO tiene 180 filas en caché y cero publicables. Servir eso como `stale` con serie vacía
    pintaría un chart en blanco — se leería como 'no hay marca que medir' en vez de 'falta
    identificar las preguntas'."""
    monkeypatch.setattr(build.BL, "fetch", lambda c: (False, []))
    monkeypatch.setattr(build.BL, "load_cache",
                        lambda: [{"country": "CO", "month": "2026-06", "experiment_id": "999",
                                  "question": None, "study_id": "s1", "exposed": 0.3}])
    m = build.collect_brand_lift("CO", now="2026-07-28T00:00:00Z")
    assert m["status"] == "not_available"
    assert "no están identificadas" in m["reason"]
    assert m.get("series") in (None, [])


def test_pais_sin_cache_y_sin_refresco_es_error(monkeypatch):
    monkeypatch.setattr(build.BL, "fetch", lambda c: (False, []))
    monkeypatch.setattr(build.BL, "load_cache", lambda: [])
    m = build.collect_brand_lift("CO", now="2026-07-28T00:00:00Z")
    assert m["status"] == "error"


def test_exit_poll_limpia_comillas_literales_de_las_opciones():
    """El formulario guarda '"Redes sociales"' con comillas dentro del valor."""
    import sources_bq
    s = sources_bq.exit_poll_series([
        {"month": "2026-07", "plaza": "MTY", "opcion": '"Redes sociales de la empresa"',
         "registros_web": "10"}])
    assert "Redes sociales de la empresa" in s[0]["opciones"]
    assert not any(k.startswith('"') for k in s[0]["opciones"])
