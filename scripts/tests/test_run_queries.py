from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_queries

REPO = Path(__file__).parent / "fixtures" / "mini_repo"

def test_discover_jobs_only_with_query():
    jobs = run_queries.discover_jobs(REPO)
    slugs = {j["slug"] for j in jobs}
    assert "cpa-diario" in slugs
    assert "incompletos-colombia" not in slugs

def test_job_applies_default_max_bytes():
    job = next(j for j in run_queries.discover_jobs(REPO) if j["slug"] == "cpa-diario")
    assert job["max_bytes"] == run_queries.DEFAULT_MAX_BYTES
    assert job["data_path"].name == "data.json"
    assert job["sql_path"].name == "query.sql"

def test_build_bq_command_includes_guardrails():
    cmd = run_queries.build_bq_command(max_bytes=5_000_000_000, project="papyrus-data")
    assert cmd[0] == "bq"
    assert "--maximum_bytes_billed=5000000000" in cmd
    assert "--format=json" in cmd
    assert "--nouse_legacy_sql" in cmd
    assert "--project_id=papyrus-data" in cmd

def test_run_job_isolates_failure(tmp_path):
    # SQL inexistente → read_text levanta; run_job debe capturarlo y devolver False
    job = {
        "slug": "bad", "folder": tmp_path,
        "sql_path": tmp_path / "missing.sql", "data_path": tmp_path / "data.json",
        "max_bytes": 1, "build_py": None,
    }
    assert run_queries.run_job(job, "papyrus-data") is False
    assert not (tmp_path / "data.json").exists()
