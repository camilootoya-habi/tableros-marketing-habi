import json, os, subprocess, sys
from pathlib import Path

DEFAULT_MAX_BYTES = 5_000_000_000  # 5 GB
DEFAULT_MAX_ROWS = 100_000          # bq default es solo 100 → trunca; subimos el tope (override con meta.max_rows)
IGNORE_DIRS = {".git", ".github", "scripts", "docs", "node_modules"}

def discover_jobs(repo_root: Path, only=None):
    """Tableros que declaran `query` en su meta.json (o tienen build.py).
    only=<slug>: corre SOLO ese tablero (ignora skip_hub_cron). Si no, omite los
    que declaran "skip_hub_cron": true (tienen su propio workflow más frecuente)."""
    repo_root = Path(repo_root)
    jobs = []
    for meta_path in sorted(repo_root.rglob("meta.json")):
        folder = meta_path.parent
        rel = folder.relative_to(repo_root)
        if rel.parts and rel.parts[0] in IGNORE_DIRS:
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if only is not None:
            if folder.name != only:
                continue
        elif meta.get("skip_hub_cron"):
            continue
        build_py = folder / "build.py"
        if not meta.get("query") and not build_py.exists():
            continue
        jobs.append({
            "slug": folder.name,
            "folder": folder,
            "sql_path": folder / meta["query"] if meta.get("query") else None,
            "data_path": folder / meta.get("data", "data.json"),
            "max_bytes": meta.get("maximum_bytes_billed", DEFAULT_MAX_BYTES),
            "max_rows": meta.get("max_rows", DEFAULT_MAX_ROWS),
            "build_py": build_py if build_py.exists() else None,
        })
    return jobs

def billing_project() -> str:
    """Proyecto que FACTURA los jobs de BQ (las tablas se leen cross-project).

    No puede ser un papyrus-*: estas credenciales perdieron `bigquery.jobs.create` en papyrus-data,
    -mx, -master y -staging, y cada query devolvía Access Denied. La variable se llama
    BQ_BILLING_PROJECT (no GCP_PROJECT) para que el secret viejo del repo no vuelva a colarse.
    """
    return os.environ.get("BQ_BILLING_PROJECT", "sellers-main-prod")


def build_bq_command(max_bytes: int, project: str, max_rows: int = DEFAULT_MAX_ROWS):
    return [
        "bq", "query", "--nouse_legacy_sql", "--format=json",
        f"--maximum_bytes_billed={max_bytes}", f"--max_rows={max_rows}", f"--project_id={project}",
    ]

def run_job(job: dict, project: str) -> bool:
    """Corre un job; True si tuvo éxito. Aísla fallos (no levanta excepción)."""
    try:
        if job["build_py"]:
            subprocess.run([sys.executable, "build.py"], cwd=job["folder"], check=True, timeout=600)
        else:
            sql = job["sql_path"].read_text(encoding="utf-8")
            cmd = build_bq_command(job["max_bytes"], project, job["max_rows"])
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
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    repo = Path(__file__).resolve().parents[1]
    project = billing_project()
    jobs = discover_jobs(repo, only=only)
    print(f"Auto-discovery{f' (--only {only})' if only else ''}: {len(jobs)} job(s) · factura en {project}")
    ok = sum(run_job(j, project) for j in jobs)
    print(f"Hecho: {ok}/{len(jobs)} OK")

if __name__ == "__main__":
    main()
