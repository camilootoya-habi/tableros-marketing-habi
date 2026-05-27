import json
from html import escape
from pathlib import Path

IGNORE_DIRS = {".git", ".github", "scripts", "docs", "node_modules"}

TEMPLATE_PATH = Path(__file__).parent / "templates" / "hub.html"

SECTION_ORDER = ["analysis", "dashboard", "reference"]
SECTION_LABELS = {"analysis": "Analysis", "dashboard": "Dashboards", "reference": "Reference"}


def render_card(d: dict) -> str:
    country = d.get("country", "")
    chips = "".join(
        f'<span class="country">{escape(c.strip())}</span>'
        for c in country.split("&")
    ) if country else ""
    return (
        f'        <a class="card" href="{escape(d["link"])}">\n'
        f'          <h2>{chips}{escape(d["title"])}</h2>\n'
        f'          <p>{escape(d["description"])}</p>\n'
        f'        </a>'
    )


def render_owner_block(heading: str, cards: list) -> str:
    columns = []
    for section in SECTION_ORDER:
        in_section = sorted(
            [c for c in cards if c.get("section", "dashboard") == section],
            key=lambda c: (c.get("order", 9999), c["title"].lower()),
        )
        if not in_section:
            continue
        cards_html = "\n\n".join(render_card(c) for c in in_section)
        columns.append(
            f'    <div class="column">\n'
            f'      <h2 class="section-title"><span>{escape(SECTION_LABELS[section])}</span></h2>\n'
            f'      <div class="card-stack">\n{cards_html}\n      </div>\n'
            f'    </div>'
        )
    columns_html = "\n".join(columns)
    return (
        f'  <h2 class="owner-title">{escape(heading)}</h2>\n'
        f'  <div class="columns">\n{columns_html}\n  </div>'
    )


def discover_dashboards(repo_root: Path):
    """Cada carpeta con meta.json es un tablero. Dueño inferido por ubicación:
    hijo directo de la raíz = 'general'; bajo canales/<lider>/ = ese líder."""
    repo_root = Path(repo_root)
    dashboards = []
    for meta_path in sorted(repo_root.rglob("meta.json")):
        rel = meta_path.parent.relative_to(repo_root)
        parts = rel.parts
        if parts and parts[0] in IGNORE_DIRS:
            continue
        if parts[0] == "canales":
            owner = parts[1]            # canales/<lider>/<slug>
            slug = parts[-1]
            link = "/".join(parts) + "/"
        else:
            owner = "general"           # <slug> en la raíz
            slug = parts[-1]
            link = "/".join(parts) + "/"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        dashboards.append({
            "slug": slug, "owner": owner, "link": link,
            "title": meta["title"], "description": meta["description"],
            "country": meta["country"], "section": meta.get("section", "dashboard"),
            "order": meta.get("order", 9999), "query": meta.get("query"),
        })
    return dashboards


def discover_leaders(repo_root: Path) -> dict:
    repo_root = Path(repo_root)
    leaders = {}
    canales = repo_root / "canales"
    if canales.exists():
        for lj in sorted(canales.glob("*/_leader.json")):
            data = json.loads(lj.read_text(encoding="utf-8"))
            leaders[lj.parent.name] = data
    return leaders


def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def build_page(dashboards, leaders, config, template) -> str:
    blocks = []
    general_cards = [d for d in dashboards if d["owner"] == "general"] + [
        {**c, "link": c["url"]} for c in config.get("external_cards", [])
    ]
    blocks.append(render_owner_block(config["general"]["title"], general_cards))
    for lid in sorted(leaders, key=lambda k: leaders[k].get("order", 9999)):
        ld = leaders[lid]
        heading = f'{ld["name"]} · {ld["channel"]}'
        lcards = [d for d in dashboards if d["owner"] == lid]
        if lcards:
            blocks.append(render_owner_block(heading, lcards))
    content = "\n".join(blocks)
    return (template
            .replace("{{TITLE}}", escape(config["title"]))
            .replace("{{SUBTITLE}}", escape(config["subtitle"]))
            .replace("{{CONTENT}}", content))


def main():
    repo = Path(__file__).resolve().parents[1]
    config = json.loads((repo / "hub.config.json").read_text(encoding="utf-8"))
    html = build_page(discover_dashboards(repo), discover_leaders(repo), config, load_template())
    (repo / "index.html").write_text(html, encoding="utf-8")
    print(f"index.html regenerado ({len(html)} bytes)")


if __name__ == "__main__":
    main()
