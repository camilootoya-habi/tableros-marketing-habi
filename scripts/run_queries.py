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

def build_bq_command(max_bytes: int, project: str):
    return [
        "bq", "query", "--nouse_legacy_sql", "--format=json",
        f"--maximum_bytes_billed={max_bytes}", f"--project_id={project}",
    ]

def run_job(job: dict, project: str) -> bool:
    """Corre un job; True si tuvo éxito. Aísla fallos (no levanta excepción)."""
    try:
        if job["build_py"]:
            subprocess.run([sys.executable, "build.py"], cwd=job["folder"], check=True, timeout=600)
        else:
            sql = job["sql_path"].read_text(encoding="utf-8")
            cmd = build_bq_command(job["max_bytes"], project)
            out = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=600)
            if out.returncode != 0:
                print(f"  ✗ {job['slug']}: {out.stderr.strip()[:300]}", file=sys.stderr)
                return False
            job["data_path"].write_text(out.stdout, encoding="utf-8")
        print(f"  ✓ {job['slug']}")
        return True
    except Exception as e:
        print(f"  ✗ {job['slug']}: {e}", file=sys.stderr)
        return False

def main():
    import os
    repo = Path(__file__).resolve().parents[1]
    project = os.environ.get("GCP_PROJECT", "papyrus-data")
    jobs = discover_jobs(repo)
    print(f"Auto-discovery: {len(jobs)} job(s)")
    ok = sum(run_job(j, project) for j in jobs)
    print(f"Hecho: {ok}/{len(jobs)} OK")

if __name__ == "__main__":
    main()
