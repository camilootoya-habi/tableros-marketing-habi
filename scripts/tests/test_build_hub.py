from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_hub

REPO = Path(__file__).parent / "fixtures" / "mini_repo"

def test_discover_dashboards_infers_owner_and_loads_meta():
    dashboards = build_hub.discover_dashboards(REPO)
    by_slug = {d["slug"]: d for d in dashboards}

    assert by_slug["incompletos-colombia"]["owner"] == "general"
    assert by_slug["incompletos-colombia"]["title"] == "Leads Incompletos"
    assert by_slug["incompletos-colombia"]["link"] == "incompletos-colombia/"

    cpa = by_slug["cpa-diario"]
    assert cpa["owner"] == "sebastian-ciendua"
    assert cpa["link"] == "canales/sebastian-ciendua/cpa-diario/"
    assert cpa["query"] == "query.sql"

def test_render_card_internal_and_country_chip():
    card = build_hub.render_card({
        "title": "CPA diario", "description": "Costo por adquisición.",
        "country": "CO", "link": "canales/sebastian-ciendua/cpa-diario/",
    })
    assert 'href="canales/sebastian-ciendua/cpa-diario/"' in card
    assert "CPA diario" in card
    assert '<span class="country">CO</span>' in card
    assert "Costo por adquisición." in card

def test_render_card_escapes_html():
    card = build_hub.render_card({
        "title": "A & B", "description": "x < y", "country": "CO", "link": "a/",
    })
    assert "A &amp; B" in card
    assert "x &lt; y" in card

SECTION_LABELS = {"analysis": "Analysis", "dashboard": "Dashboards", "reference": "Reference"}

def test_build_page_orders_general_then_leaders():
    dashboards = build_hub.discover_dashboards(REPO)
    leaders = build_hub.discover_leaders(REPO)
    config = {"title": "Growth & Marketing", "subtitle": "sub", "general": {"title": "General · Marketing", "order": 0}, "external_cards": []}
    html = build_hub.build_page(dashboards, leaders, config, template=build_hub.load_template())
    assert "NO editar a mano" in html
    assert "Growth &amp; Marketing" in html or "Growth & Marketing" in html
    assert html.index("General · Marketing") < html.index("Sebastián Ciendua · Performance Colombia")
    assert "canales/sebastian-ciendua/cpa-diario/" in html

def test_discover_leaders_reads_leader_json():
    leaders = build_hub.discover_leaders(REPO)
    assert leaders["sebastian-ciendua"]["name"] == "Sebastián Ciendua"
    assert leaders["sebastian-ciendua"]["channel"] == "Performance Colombia"

def test_build_page_renders_external_card_under_analysis():
    config = {
        "title": "T", "subtitle": "s", "general": {"title": "General", "order": 0},
        "external_cards": [{
            "section": "analysis", "order": 1, "title": "Informe externo",
            "description": "d", "country": "CO", "url": "https://example.com/x/",
        }],
    }
    html = build_hub.build_page([], {}, config, template=build_hub.load_template())
    assert 'href="https://example.com/x/"' in html
    assert "Informe externo" in html
    assert ">Analysis<" in html

def test_render_owner_block_groups_by_section_in_order():
    cards = [
        {"title": "B dash", "description": "", "country": "CO", "link": "b/", "section": "dashboard", "order": 2},
        {"title": "A dash", "description": "", "country": "CO", "link": "a/", "section": "dashboard", "order": 1},
        {"title": "An analysis", "description": "", "country": "CO", "link": "an/", "section": "analysis", "order": 1},
    ]
    html = build_hub.render_owner_block("General · Marketing", cards)
    assert "General · Marketing" in html
    assert html.index(">Analysis<") < html.index(">Dashboards<")
    assert html.index("A dash") < html.index("B dash")
