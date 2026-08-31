import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_brand_lift as BL

RESULT = json.dumps({
    "cell_id": "987465497325149", "experiment_id": "1380313597249074",
    "scoreMean.test": 0.28415, "scoreMean.control": 0.33241,
    "scoreMean.incremental": -0.04826, "brandLiftCILower": -0.08962,
    "brandLiftCIUpper": -0.00212, "responders.test": 689, "responders.control": 676,
    "breakthroughs.singleCellBayesianConfidence": 0.05, "spend": 140867.87,
    "scoreMeanRegion": 0.01017, "scoreMeanVertical": None,
})
STUDY = {"id": "2539254759864543", "name": "HABI MX - Continuous Brand Lift (Jul 2026-Jul 2026)",
         "type": "LIFT", "start_time": "2026-07-01T07:00:00+0000",
         "end_time": "2026-08-01T06:59:59+0000",
         "objectives": {"data": [{"id": "1376237287787800", "type": "BRAND",
                                  "results": [RESULT]}]}}

def test_parse_desenvuelve_el_json_anidado_en_string():
    rows = BL.parse_results([STUDY], "MX")
    assert len(rows) == 1
    r = rows[0]
    assert r["country"] == "MX" and r["month"] == "2026-07"
    assert round(r["exposed"], 5) == 0.28415
    assert round(r["lift"], 5) == -0.04826
    assert r["experiment_id"] == "1380313597249074"

def test_resultado_sin_experiment_id_se_descarta():
    s = dict(STUDY)
    s["objectives"] = {"data": [{"id": "x", "type": "BRAND",
                                 "results": [json.dumps({"cell_id": "1"})]}]}
    assert BL.parse_results([s], "MX") == []

def test_estudio_no_lift_se_ignora():
    s = dict(STUDY, type="SPLIT_TEST_V2")
    assert BL.parse_results([s], "MX") == []

def test_series_agrupa_por_mes_y_pregunta():
    rows = BL.parse_results([STUDY], "MX")
    rows[0]["question"] = "ad_recall"
    s = BL.series(rows)
    assert s[0]["month"] == "2026-07" and s[0]["question"] == "ad_recall"


# --- fetch() devuelve (ok, rows) — Task 5 defecto 1: el llamador necesita distinguir un
# refresco exitoso de uno degradado para no mentir con el timestamp. ---

def test_fetch_ok_devuelve_ok_true_y_las_filas_parseadas(monkeypatch):
    monkeypatch.setattr(BL, "_get", lambda path, **params: (True, {"data": [STUDY]}))
    ok, rows = BL.fetch("MX")
    assert ok is True
    assert len(rows) == 1 and rows[0]["experiment_id"] == "1380313597249074"


def test_fetch_fallo_devuelve_ok_false_y_filas_vacias(monkeypatch):
    monkeypatch.setattr(BL, "_get", lambda path, **params:
                         (False, {"error": {"message": "rate limited", "is_transient": True}}))
    ok, rows = BL.fetch("MX")
    assert ok is False
    assert rows == []


# --- merge_rows() — Task 5 defecto 2: el caché nunca debe encogerse y un estudio que
# reaparece en la página se actualiza in place, no se duplica. ---

CACHED_A = {"country": "MX", "month": "2026-01", "question": None, "experiment_id": "1",
            "exposed": 0.10}
CACHED_B = {"country": "MX", "month": "2026-02", "question": None, "experiment_id": "2",
            "exposed": 0.20}


def test_merge_rows_agrega_fila_nueva_sin_tocar_las_existentes():
    fresh = [{"country": "MX", "month": "2026-03", "question": None, "experiment_id": "3",
              "exposed": 0.30}]
    merged = BL.merge_rows([CACHED_A, CACHED_B], fresh)
    assert len(merged) == 3
    assert {r["experiment_id"] for r in merged} == {"1", "2", "3"}


def test_merge_rows_actualiza_in_place_por_la_misma_identidad_sin_duplicar():
    # misma (country, month, question, experiment_id) que CACHED_A, pero con un valor nuevo:
    # un estudio que reaparece en la página se sobreescribe, no se duplica.
    fresh = [{"country": "MX", "month": "2026-01", "question": None, "experiment_id": "1",
              "exposed": 0.99}]
    merged = BL.merge_rows([CACHED_A, CACHED_B], fresh)
    assert len(merged) == 2
    actualizada = [r for r in merged if r["experiment_id"] == "1"][0]
    assert actualizada["exposed"] == 0.99


def test_merge_rows_nunca_encoge_el_cache():
    # la página trae menos estudios de los que ya hay en el caché (p.ej. uno viejo salió
    # de los 10 más recientes) — el merge debe conservar TODO el histórico, nunca truncar.
    cached = [CACHED_A, CACHED_B,
              {"country": "MX", "month": "2026-03", "question": None, "experiment_id": "3",
               "exposed": 0.30}]
    fresh = [dict(CACHED_A, exposed=0.11)]     # la página de hoy solo trae 1 de los 3
    merged = BL.merge_rows(cached, fresh)
    assert len(merged) == len(cached)
    assert {r["experiment_id"] for r in merged} == {"1", "2", "3"}


def test_merge_rows_sin_fresh_conserva_el_cache_completo():
    merged = BL.merge_rows([CACHED_A, CACHED_B], [])
    assert len(merged) == 2


# --- save_cache() / load_last_refresh() — el timestamp de refresco exitoso vive en el mismo
# archivo, junto a "rows", para que build.py pueda servir un "stale" honesto. ---

def test_save_cache_y_load_cache_hacen_roundtrip(monkeypatch, tmp_path):
    cache_path = tmp_path / "brand_lift_cache.json"
    monkeypatch.setattr(BL, "CACHE", str(cache_path))
    BL.save_cache([CACHED_A, CACHED_B], {"MX": "2026-07-27T18:00:00Z"})
    assert BL.load_cache() == [CACHED_A, CACHED_B]
    assert BL.load_last_refresh() == {"MX": "2026-07-27T18:00:00Z"}


def test_load_last_refresh_sin_archivo_devuelve_vacio(monkeypatch, tmp_path):
    monkeypatch.setattr(BL, "CACHE", str(tmp_path / "no_existe.json"))
    assert BL.load_last_refresh() == {}


def test_load_cache_sigue_devolviendo_solo_la_lista_de_filas(monkeypatch, tmp_path):
    # contrato existente: load_cache() no debe empezar a exigir que los llamadores sepan de
    # last_refresh — solo agrega una llave, no cambia la forma de la que ya depende el resto.
    cache_path = tmp_path / "brand_lift_cache.json"
    monkeypatch.setattr(BL, "CACHE", str(cache_path))
    BL.save_cache([CACHED_A], {"MX": "2026-07-27T18:00:00Z"})
    rows = BL.load_cache()
    assert isinstance(rows, list)
    assert rows == [CACHED_A]


# ── Mes del estudio: del NOMBRE, no del start_time ────────────────────────────
# Los estudios recurrentes arrancan el día 29. Febrero no tiene 29, así que el estudio
# "Feb-Mar" arranca el 1 de MARZO y `start_time[:7]` lo mandaba a marzo: dos estudios en el
# mismo mes y febrero desaparecido. Pasó en 2023-03, 2025-03 y 2026-03 de CO. El nombre
# ("Feb 2023-Mar 2023") sí lo dice sin ambigüedad, así que es la fuente correcta.

def test_mes_sale_del_nombre_no_del_start_time():
    estudios = [{
        "id": "1537329786743415", "type": "LIFT",
        "name": "Habi: Continuous Brand Lift (Feb 2023-Mar 2023)",
        "start_time": "2023-03-01T05:00:00+0000",
        "objectives": {"data": [{"results": [json.dumps({
            "experiment_id": "1", "scoreMean.test": 0.4})]}]},
    }]
    assert BL.parse_results(estudios, "CO")[0]["month"] == "2023-02"


def test_dos_estudios_solapados_caen_en_meses_distintos():
    def est(sid, nombre, start, exp):
        return {"id": sid, "type": "LIFT", "name": nombre, "start_time": start,
                "objectives": {"data": [{"results": [json.dumps({
                    "experiment_id": exp, "scoreMean.test": 0.4})]}]}}
    estudios = [
        est("A", "Habi: Continuous Brand Lift (Feb 2026-Mar 2026)", "2026-03-01T05:00:00+0000", "1"),
        est("B", "Habi: Continuous Brand Lift (Mar 2026-Apr 2026)", "2026-03-29T05:00:00+0000", "2"),
    ]
    meses = sorted(r["month"] for r in BL.parse_results(estudios, "CO"))
    assert meses == ["2026-02", "2026-03"]


def test_nombre_sin_mes_reconocible_cae_al_start_time():
    """Un nombre que no trae mes no debe romper nada: se vuelve al comportamiento viejo."""
    estudios = [{
        "id": "X", "type": "LIFT", "name": "Un estudio sin fecha en el nombre",
        "start_time": "2024-08-29T05:00:00+0000",
        "objectives": {"data": [{"results": [json.dumps({
            "experiment_id": "1", "scoreMean.test": 0.4})]}]},
    }]
    assert BL.parse_results(estudios, "MX")[0]["month"] == "2024-08"


def test_nombre_de_un_solo_mes():
    """MX usa "(Mes AAAA)" sin rango. Debe leerse igual."""
    estudios = [{
        "id": "Y", "type": "LIFT", "name": "HABI MX - Continuous Brand Lift (Abr 2025)",
        "start_time": "2025-05-01T05:00:00+0000",
        "objectives": {"data": [{"results": [json.dumps({
            "experiment_id": "1", "scoreMean.test": 0.4})]}]},
    }]
    assert BL.parse_results(estudios, "MX")[0]["month"] == "2025-04"
