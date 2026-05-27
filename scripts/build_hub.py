import json
from pathlib import Path

IGNORE_DIRS = {".git", ".github", "scripts", "docs", "node_modules"}


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
