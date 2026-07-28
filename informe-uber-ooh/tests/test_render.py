import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import render  # noqa: E402


def _write(tmp, rel, text):
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ── Capítulos: merge base + mes ───────────────────────────────────────────────

def test_orden_por_prefijo_numerico(tmp_path):
    _write(tmp_path, "base/02-rigor.md", "# Rigor\nbase")
    _write(tmp_path, "base/01-resumen.md", "# Resumen\nbase")
    ch = render.chapters_for("2026-07", str(tmp_path))
    assert [c["order"] for c in ch] == [1, 2]
    assert ch[0]["title"] == "Resumen"


def test_archivo_del_mes_reemplaza_al_de_base(tmp_path):
    _write(tmp_path, "base/01-resumen.md", "# Resumen\nviejo")
    _write(tmp_path, "2026-07/01-resumen.md", "# Resumen\nnuevo")
    ch = render.chapters_for("2026-07", str(tmp_path))
    assert len(ch) == 1 and "nuevo" in ch[0]["body"]


def test_archivo_nuevo_del_mes_agrega_capitulo(tmp_path):
    _write(tmp_path, "base/01-resumen.md", "# Resumen\nbase")
    _write(tmp_path, "2026-07/07-propuesta.md", "# Propuesta\nQ3")
    assert [c["order"] for c in render.chapters_for("2026-07", str(tmp_path))] == [1, 7]


def test_el_mes_de_otro_periodo_no_se_mezcla(tmp_path):
    _write(tmp_path, "base/01-resumen.md", "# Resumen\nbase")
    _write(tmp_path, "2026-06/07-vieja.md", "# Vieja\njunio")
    assert len(render.chapters_for("2026-07", str(tmp_path))) == 1


# ── Interpolación ─────────────────────────────────────────────────────────────

DATA = {"metrics": {
    "exit_poll": {"MX": {"status": "ok", "series": [
        {"month": "2026-06", "plaza": "MTY", "registros_web": 100, "respuestas": 80, "tasa": .8,
         "opciones": {"Vehículos de Uber": 4}},
        {"month": "2026-06", "plaza": "GDL", "registros_web": 100, "respuestas": 20, "tasa": .2,
         "opciones": {"Vehículos de Uber": 1}},
        {"month": "2026-07", "plaza": "MTY", "registros_web": 100, "respuestas": 50, "tasa": .5,
         "opciones": {"Vehículos de Uber": 5}},
    ]}},
    "brand_lift": {"MX": {"status": "stale", "series": [
        {"month": "2026-06", "question": "ad_recall", "exposed": .35, "control": .16, "lift": .19},
        {"month": "2026-07", "question": "ad_recall", "exposed": .25, "control": .14, "lift": .11},
        {"month": "2026-07", "question": "toma", "exposed": .17, "control": .12, "lift": .05},
    ]}},
    "traffic": {"MX": {"status": "ok", "series": [
        {"month": "2026-07", "plaza": "MTY", "users": 1000, "spend": 2500.0, "cpv": 2.5},
        {"month": "2026-07", "plaza": "GDL", "users": 1000, "spend": None, "cpv": None},
    ]},
        "CO": {"status": "not_available", "reason": "Sin export de GA4 usable para CO."}},
}}


def test_interpola_con_dimension_de_plaza():
    assert render.interpolate("{{exit_poll.MX.MTY.tasa.latest:pct1}}", DATA) == "50.0%"


def test_sin_dimension_agrega_todas_las_plazas():
    """junio: 80+20 respuestas sobre 100+100 registros = 50%."""
    assert render.interpolate("{{exit_poll.MX.tasa.latest:pct1}}", DATA) == "50.0%"
    assert render.interpolate("{{exit_poll.MX.uber.latest:num}}", DATA) == "5"


def test_selector_max_encuentra_el_pico_no_el_ultimo():
    assert render.interpolate("{{brand_lift.MX.ad_recall.lift.max:pts}}", DATA) == "+19.0 pts"
    assert render.interpolate("{{brand_lift.MX.ad_recall.exposed.max:pct1}}", DATA) == "35.0%"


def test_month_devuelve_el_mes_del_dato_citado():
    assert render.interpolate("{{brand_lift.MX.ad_recall.lift.max:month}}", DATA) == "2026-06"
    assert render.interpolate("{{brand_lift.MX.ad_recall.lift.latest:month}}", DATA) == "2026-07"


def test_stale_si_se_puede_citar():
    """Un dato vencido sigue siendo un dato real; lo que no se puede citar es lo que no existe."""
    assert render.interpolate("{{brand_lift.MX.toma.lift.latest:pts}}", DATA) == "+5.0 pts"


def test_metrica_not_available_aborta_en_vez_de_poner_cero():
    with pytest.raises(render.UnresolvedPlaceholder) as e:
        render.interpolate("{{traffic.CO.users.latest:num}}", DATA)
    assert "not_available" in str(e.value)


def test_campo_none_aborta():
    """GDL no tiene inversión: citar su CPV debe fallar, no imprimir 0."""
    with pytest.raises(render.UnresolvedPlaceholder):
        render.interpolate("{{traffic.MX.GDL.cpv.latest:money}}", DATA)


def test_dimension_inexistente_aborta():
    with pytest.raises(render.UnresolvedPlaceholder) as e:
        render.interpolate("{{brand_lift.MX.favorabilidad.lift.latest:pts}}", DATA)
    assert "favorabilidad" in str(e.value)


def test_ruta_mal_formada_aborta():
    with pytest.raises(render.UnresolvedPlaceholder):
        render.interpolate("{{exit_poll.MX.tasa}}", DATA)


def test_texto_sin_placeholders_pasa_intacto():
    assert render.interpolate("sin nada", DATA) == "sin nada"


# ── Bloques y markdown ────────────────────────────────────────────────────────

MD = """Texto antes.

```chart
metrica: brand_lift
pais: MX
vista: lift
caption: Gráfica 2 — histórico
```

Texto después.
"""


def test_extrae_el_bloque_y_deja_marcador():
    body, blocks = render.parse_blocks(MD)
    assert len(blocks) == 1
    assert blocks[0]["metrica"] == "brand_lift" and blocks[0]["caption"] == "Gráfica 2 — histórico"
    assert "@@BLOCK0@@" in body and "```" not in body


def test_bloque_sin_metrica_valida_es_error_de_autoria():
    with pytest.raises(render.BadBlock):
        render.parse_blocks("```chart\nvista: lift\npais: MX\n```")
    with pytest.raises(render.BadBlock):
        render.parse_blocks("```chart\nmetrica: inventada\npais: MX\nvista: lift\n```")


def test_bloque_sin_pais_es_error():
    with pytest.raises(render.BadBlock):
        render.parse_blocks("```chart\nmetrica: traffic\nvista: cpv\n```")


def test_bloque_sin_vista_es_error():
    """Una vista ausente dejaría un canvas en blanco en el documento y nadie lo notaría."""
    with pytest.raises(render.BadBlock):
        render.parse_blocks("```chart\nmetrica: traffic\npais: MX\n```")
    with pytest.raises(render.BadBlock):
        render.parse_blocks("```chart\nmetrica: traffic\npais: MX\nvista: inventada\n```")


def test_markdown_basico():
    html = render.md_to_html("## Sub\n\n- uno\n- dos\n\nPárrafo con **negrita** y *cursiva*.")
    assert "<h2>Sub</h2>" in html
    assert "<li>uno</li>" in html and "<li>dos</li>" in html
    assert "<strong>negrita</strong>" in html and "<em>cursiva</em>" in html


def test_markdown_tabla():
    html = render.md_to_html("| Región | Autos |\n| --- | --- |\n| CDMX | 100 |\n| MTY | 50 |")
    assert "<th>Región</th>" in html and "<td>CDMX</td>" in html
    assert "---" not in html


def test_markdown_escapa_html_del_editorial():
    assert "&lt;script&gt;" in render.md_to_html("Ojo con <script>alert(1)</script>")


def test_link_se_convierte():
    assert '<a href="https://x.com"' in render.md_to_html("Ver [esto](https://x.com)")


def test_parrafo_con_salto_suave_se_une():
    """Sin unir, un énfasis que cruza el wrap deja los asteriscos a la vista."""
    html = render.md_to_html('El mensaje *"Monterrey, ya llegamos:\nde norte a sur"* humanizó.')
    assert html.count("<p>") == 1
    assert "<em>" in html and "*" not in html


def test_item_de_lista_con_salto_suave_se_une():
    html = render.md_to_html("- **Narrativa local.** El mensaje *abre\ny cierra* aquí.\n- otro")
    assert html.count("<li>") == 2
    assert "<em>abre y cierra</em>" in html
    assert "*" not in html


def test_linea_en_blanco_separa_parrafos():
    html = render.md_to_html("uno\ndos\n\ntres")
    assert html.count("<p>") == 2 and "<p>uno dos</p>" in html


def test_encabezado_corta_el_parrafo_anterior():
    html = render.md_to_html("texto\n## Titulo\nmas texto")
    assert html.index("<p>texto</p>") < html.index("<h2>Titulo</h2>") < html.index("<p>mas texto</p>")


def test_tabla_despues_de_lista_cierra_la_lista():
    html = render.md_to_html("- a\n\n| X |\n| --- |\n| 1 |")
    assert html.index("</ul>") < html.index("<table>")
