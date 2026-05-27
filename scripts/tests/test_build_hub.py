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
