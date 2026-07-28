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


# ── Compuerta de cuota: el cron corre cada 4h, la API se llama 1 vez al día ────

def test_refresco_reciente_evita_la_llamada(monkeypatch):
    """12 llamadas diarias por país a una cuenta de producción, para datos mensuales, es gasto puro."""
    llamadas = []
    monkeypatch.setattr(build.BL, "fetch", lambda c: (llamadas.append(c), (True, []))[1])
    monkeypatch.setattr(build.BL, "load_last_refresh", lambda: {"MX": "2026-07-28T00:00:00Z"})
    monkeypatch.setattr(build.BL, "load_cache",
                        lambda: [{"country": "MX", "month": "2026-07", "experiment_id": "e1",
                                  "question": None, "study_id": "s1", "exposed": 0.3}])
    monkeypatch.setattr(build.BL, "map_questions",
                        lambda rows, mapping=None: [dict(r, question="ad_recall") for r in rows])
    m = build.collect_brand_lift("MX", now="2026-07-28T06:00:00Z")   # mismo día UTC
    assert llamadas == [], "no debió llamar a la API"
    assert m["status"] == "ok" and m["source"] == "cache"
    assert m["last_updated"] == "2026-07-28T00:00:00Z"


def test_refresco_viejo_si_llama(monkeypatch):
    llamadas = []
    monkeypatch.setattr(build.BL, "fetch", lambda c: (llamadas.append(c), (False, []))[1])
    monkeypatch.setattr(build.BL, "load_last_refresh", lambda: {"MX": "2026-07-26T00:00:00Z"})
    monkeypatch.setattr(build.BL, "load_cache", lambda: [])
    build.collect_brand_lift("MX", now="2026-07-28T06:00:00Z")       # otro día UTC
    assert llamadas == ["MX"]


def test_sin_refresco_previo_si_llama(monkeypatch):
    llamadas = []
    monkeypatch.setattr(build.BL, "fetch", lambda c: (llamadas.append(c), (False, []))[1])
    monkeypatch.setattr(build.BL, "load_last_refresh", lambda: {})
    monkeypatch.setattr(build.BL, "load_cache", lambda: [])
    build.collect_brand_lift("MX", now="2026-07-28T06:00:00Z")
    assert llamadas == ["MX"]


def test_veinte_horas_el_mismo_dia_no_dispara_segunda_llamada(monkeypatch):
    """El bug que encontró la revisión final: con umbral de 20 h y cron cada 4 h, un refresco a
    la hora 0 volvía a ser elegible a la hora 20 del MISMO día → 2 llamadas en un día a una
    cuenta de producción. Comparar la fecha UTC lo cierra sin depender del cron."""
    llamadas = []
    monkeypatch.setattr(build.BL, "fetch", lambda c: (llamadas.append(c), (True, []))[1])
    monkeypatch.setattr(build.BL, "load_last_refresh", lambda: {"MX": "2026-07-28T00:00:00Z"})
    monkeypatch.setattr(build.BL, "load_cache",
                        lambda: [{"country": "MX", "month": "2026-07", "experiment_id": "e1",
                                  "question": None, "study_id": "s1", "exposed": 0.3}])
    monkeypatch.setattr(build.BL, "map_questions",
                        lambda rows, mapping=None: [dict(r, question="ad_recall") for r in rows])
    build.collect_brand_lift("MX", now="2026-07-28T20:00:00Z")
    assert llamadas == []


def test_a_lo_mas_una_llamada_por_dia_sobre_un_mes_de_cron(monkeypatch):
    """Simula el cron real (cada 4 h) durante 30 días y cuenta llamadas por día calendario."""
    import datetime as dt
    estado = {"MX": None}
    llamadas = []
    monkeypatch.setattr(build.BL, "load_cache", lambda: [])
    monkeypatch.setattr(build.BL, "load_last_refresh", lambda: dict(
        {k: v for k, v in estado.items() if v}))

    def fake_fetch(c):
        llamadas.append(ahora[0])
        return False, []          # falla: no persiste, pero sí cuenta la llamada
    monkeypatch.setattr(build.BL, "fetch", fake_fetch)

    ahora = [None]
    t = dt.datetime(2026, 1, 1, 0, 0, 0)
    for _ in range(30 * 6):       # 30 días × 6 corridas diarias
        ahora[0] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        if not build._refresco_reciente(estado["MX"], ahora[0]):
            fake_fetch("MX")
            estado["MX"] = ahora[0]     # simula el éxito que persistiría el timestamp
        t += dt.timedelta(hours=4)

    por_dia = {}
    for c in llamadas:
        por_dia[c[:10]] = por_dia.get(c[:10], 0) + 1
    assert max(por_dia.values()) == 1, f"días con más de una llamada: {[d for d, n in por_dia.items() if n > 1]}"
    assert len(por_dia) == 30


# ── Mes en curso: el estudio abierto no es un dato cerrado ─────────────────────

def test_marca_parcial_el_estudio_que_no_cerro():
    s = build.marca_parciales([
        {"month": "2026-06", "end_time": "2026-07-01T06:59:59+0000"},
        {"month": "2026-07", "end_time": "2026-08-01T06:59:59+0000"},
    ], now="2026-07-27T00:00:00Z")
    assert s[0]["parcial"] is False
    assert s[1]["parcial"] is True


def test_sin_end_time_no_se_marca_parcial():
    """Ausencia de dato no es evidencia de mes en vuelo: se asume cerrado."""
    s = build.marca_parciales([{"month": "2026-07"}], now="2026-07-27T00:00:00Z")
    assert s[0]["parcial"] is False


def test_el_dia_del_cierre_ya_no_es_parcial():
    s = build.marca_parciales([{"month": "2026-07", "end_time": "2026-08-01T06:59:59+0000"}],
                              now="2026-08-01T12:00:00Z")
    assert s[0]["parcial"] is False
