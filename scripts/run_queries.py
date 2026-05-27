import json, subprocess, sys
from pathlib import Path

DEFAULT_MAX_BYTES = 5_000_000_000  # 5 GB
IGNORE_DIRS = {".git", ".github", "scripts", "docs", "node_modules"}

def discover_jobs(repo_root: Path):
    """Tableros que declaran `query` en su meta.json (o tienen build.py)."""
    repo_root = Path(repo_root)
    jobs = []
    for meta_path in sorted(repo_root.rglob("meta.json")):
        folder = meta_path.parent
        rel = folder.relative_to(repo_root)
        if rel.parts and rel.parts[0] in IGNORE_DIRS:
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        build_py = folder / "build.py"
        if not meta.get("query") and not build_py.exists():
            continue
        jobs.append({
            "slug": folder.name,
            "folder": folder,
            "sql_path": folder / meta["query"] if meta.get("query") else None,
            "data_path": folder / meta.get("data", "data.json"),
            "max_bytes": meta.get("maximum_bytes_billed", DEFAULT_MAX_BYTES),
            "build_py": build_py if build_py.exists() else None,
        })
    return jobs
