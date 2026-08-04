import json
import sys
import unicodedata
from html import escape
from pathlib import Path

IGNORE_DIRS = {".git", ".github", "scripts", "docs", "node_modules"}

TEMPLATE_PATH = Path(__file__).parent / "templates" / "hub.html"

SECTION_ORDER = ["analysis", "dashboard", "reference"]
SECTION_LABELS = {"analysis": "Analysis", "dashboard": "Dashboards", "reference": "Reference"}

DEFAULT_TABS = [{"id": "marketing-general", "label": "Marketing General", "order": 0}]


def slugify(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return "-".join(norm.lower().split())


SECTION_TO_TAB = {"analysis": "documentos", "reference": "referencias"}


def resolve_tab(dashboard: dict, leaders: dict) -> str:
    """Pestaña de un tablero: override `tab` explícito gana. Si es general, su
    `section` decide (analysis→documentos, reference→referencias, resto→marketing-general).
    Si es de un líder, slug de su `channel`; sin channel, cae a marketing-general."""
    if dashboard.get("tab"):
        return dashboard["tab"]
    if dashboard["owner"] == "general":
        return SECTION_TO_TAB.get(dashboard.get("section", "dashboard"), "marketing-general")
    channel = leaders.get(dashboard["owner"], {}).get("channel", "")
    return slugify(channel) if channel else "marketing-general"


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
    hijo directo de la raíz = 'general'; bajo canales/<lider>/ = ese líder.
    Un meta.json malformado o incompleto se salta con warning, para no tumbar
    la regeneración del hub entero por culpa del tablero de un solo líder."""
    repo_root = Path(repo_root)
    dashboards = []
    for meta_path in sorted(repo_root.rglob("meta.json")):
        rel = meta_path.parent.relative_to(repo_root)
        parts = rel.parts
        if not parts or parts[0] in IGNORE_DIRS:
            continue
        owner = parts[1] if parts[0] == "canales" else "general"
        slug = parts[-1]
        link = "/".join(parts) + "/"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            dashboards.append({
                "slug": slug, "owner": owner, "link": link,
                "title": meta["title"], "description": meta["description"],
                "country": meta["country"], "section": meta.get("section", "dashboard"),
                "order": meta.get("order", 9999), "query": meta.get("query"),
                "tab": meta.get("tab"),
            })
        except (ValueError, KeyError, OSError) as e:
            print(f"  ⚠ meta inválido, se salta: {meta_path} ({e})", file=sys.stderr)
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


def render_empty_panel() -> str:
    return ('    <div class="empty-state">Próximamente — aún no hay tableros en '
            'esta sección.</div>')


def render_tab_content(tab_id, tab_label, dashboards, leaders, config) -> str:
    """Owner-blocks dentro de una pestaña: general primero, luego líderes por order.
    Las external_cards cuelgan de la pestaña que declaren en `tab`, o de
    marketing-general si no la declaran. El título del bloque general es la
    etiqueta de la propia pestaña (no un texto fijo)."""
    blocks = []
    general_cards = [d for d in dashboards if d["owner"] == "general"]
    externals = [
        {**c, "link": c["url"]}
        for c in config.get("external_cards", [])
        if c.get("tab", "marketing-general") == tab_id
    ]
    general_cards = general_cards + externals
    if general_cards:
        blocks.append(render_owner_block(tab_label, general_cards))
    for lid in sorted(leaders, key=lambda k: leaders[k].get("order", 9999)):
        lcards = [d for d in dashboards if d["owner"] == lid]
        if lcards:
            ld = leaders[lid]
            blocks.append(render_owner_block(f'{ld["name"]} · {ld["channel"]}', lcards))
    return "\n".join(blocks) if blocks else render_empty_panel()


def build_page(dashboards, leaders, config, template) -> str:
    tabs = sorted(config.get("tabs", DEFAULT_TABS), key=lambda t: t.get("order", 9999))
    valid_ids = {t["id"] for t in tabs}
    for d in dashboards:
        tid = resolve_tab(d, leaders)
        if tid not in valid_ids:
            print(f"  ⚠ tab '{tid}' no está en config.tabs; {d['slug']} → marketing-general",
                  file=sys.stderr)
            tid = "marketing-general"
        d["_tab"] = tid

    tab_bar, panels = [], []
    for i, t in enumerate(tabs):
        active = " active" if i == 0 else ""
        gcls = f' tab-{t["group"]}' if t.get("group") else ""
        tab_bar.append(
            f'    <button type="button" class="tab-btn{gcls}{active}" '
            f'data-tab="{escape(t["id"])}">{escape(t["label"])}</button>'
        )
        in_tab = [d for d in dashboards if d["_tab"] == t["id"]]
        content = render_tab_content(t["id"], t["label"], in_tab, leaders, config)
        panels.append(
            f'  <div class="tab-panel{active}" id="panel-{escape(t["id"])}">\n'
            f'{content}\n  </div>'
        )

    return (template
            .replace("{{TITLE}}", escape(config["title"]))
            .replace("{{SUBTITLE}}", escape(config["subtitle"]))
            .replace("{{TABS}}", "\n".join(tab_bar))
            .replace("{{PANELS}}", "\n".join(panels)))


def main():
    repo = Path(__file__).resolve().parents[1]
    config = json.loads((repo / "hub.config.json").read_text(encoding="utf-8"))
    html = build_page(discover_dashboards(repo), discover_leaders(repo), config, load_template())
    (repo / "index.html").write_text(html, encoding="utf-8")
    print(f"index.html regenerado ({len(html)} bytes)")


if __name__ == "__main__":
    main()
