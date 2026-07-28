import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import build  # noqa: E402


def test_solo_escribe_el_mes_pedido(tmp_path):
    """Lo que hace inmutable una edición pasada: nadie la vuelve a escribir."""
    (tmp_path / "2026-06").mkdir()
    viejo = tmp_path / "2026-06" / "index.html"
    viejo.write_text("EDICION DE JUNIO", encoding="utf-8")
    build.write_edition("2026-07", root=str(tmp_path), html="<p>julio</p>")
    assert viejo.read_text(encoding="utf-8") == "EDICION DE JUNIO"
    assert (tmp_path / "2026-07" / "index.html").exists()


def test_indice_lista_de_mas_nueva_a_mas_vieja(tmp_path):
    for m in ("2026-06", "2026-07", "2026-05"):
        (tmp_path / m).mkdir()
        (tmp_path / m / "index.html").write_text("x", encoding="utf-8")
    assert build.editions(str(tmp_path)) == ["2026-07", "2026-06", "2026-05"]


def test_el_indice_ignora_carpetas_que_no_son_meses(tmp_path):
    for d in ("assets", "contenido", "tests", "2026-07"):
        (tmp_path / d).mkdir()
    (tmp_path / "2026-07" / "index.html").write_text("x", encoding="utf-8")
    assert build.editions(str(tmp_path)) == ["2026-07"]


def test_carpeta_de_mes_sin_index_no_cuenta_como_edicion(tmp_path):
    (tmp_path / "2026-07").mkdir()
    assert build.editions(str(tmp_path)) == []


DATA = {"metrics": {"exit_poll": {"MX": {"status": "ok", "series": [
    {"month": "2026-07", "plaza": "MTY", "registros_web": 100, "respuestas": 70, "tasa": .7,
     "opciones": {"Vehículos de Uber": 3}}]}}}}

PLANTILLA = ("<html><!--MONTH--><ol><!--INDICE--></ol><!--CHAPTERS-->"
             "<script>const D=<!--DATA-->,C=<!--CHARTS-->;</script></html>")


def test_build_html_hornea_las_cifras_y_los_slots(tmp_path):
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "01-resumen.md").write_text(
        "# Resumen\nLa tasa fue {{exit_poll.MX.MTY.tasa.latest:pct1}}.", encoding="utf-8")
    html = build.build_html("2026-07", DATA, PLANTILLA, contenido=str(tmp_path))
    assert "70.0%" in html
    assert "{{" not in html and "<!--" not in html
    assert "2026-07" in html and "Resumen" in html


def test_placeholder_sin_resolver_aborta_el_render(tmp_path):
    """Vale más no publicar que publicar un cero inventado en un documento de comité."""
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "01-resumen.md").write_text(
        "# Resumen\nCito {{traffic.CO.users.latest:num}}.", encoding="utf-8")
    try:
        build.build_html("2026-07", DATA, PLANTILLA, contenido=str(tmp_path))
    except SystemExit as e:
        assert "01-resumen" in str(e)
    else:
        raise AssertionError("debió abortar")


def test_bloque_chart_se_convierte_en_canvas(tmp_path):
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "01-c.md").write_text(
        "# C\nTexto.\n\n```chart\nmetrica: exit_poll\npais: MX\nvista: share\ncaption: Gráfica 1\n```",
        encoding="utf-8")
    html = build.build_html("2026-07", DATA, PLANTILLA, contenido=str(tmp_path))
    assert '<canvas id="c0">' in html and "Gráfica 1" in html
    assert '"vista": "share"' in html or '"vista":"share"' in html
