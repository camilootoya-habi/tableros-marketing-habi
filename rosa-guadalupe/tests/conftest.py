"""Ningún test llama a Meta ni escribe los archivos versionados del tablero."""
import importlib.util
import pathlib
import sys

import pytest

# Con nombre propio: salud-marca también tiene un `build.py` y las dos suites corren juntas.
_spec = importlib.util.spec_from_file_location("rosa_build", pathlib.Path(__file__).resolve().parents[1] / "build.py")
B = importlib.util.module_from_spec(_spec)
sys.modules["rosa_build"] = B
_spec.loader.exec_module(B)


@pytest.fixture(autouse=True)
def sin_red_ni_archivos(tmp_path, monkeypatch):
    for v in ("META_SYSTEM_USER_TOKEN", "META_PCOM_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(B, "CACHE", str(tmp_path / "cache.json"))
    monkeypatch.setattr(B, "DATA", str(tmp_path / "data.json"))
    monkeypatch.setattr(B, "MINIATURAS", str(tmp_path / "miniaturas"))
    monkeypatch.setattr(B, "SOCIAL_CACHE", str(tmp_path / "social_cache.json"))
    # La config real, copiada: los tests no dependen de que alguien edite incluir/excluir.
    cfg = tmp_path / "config.json"
    cfg.write_text(pathlib.Path(B.CONFIG).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(B, "CONFIG", str(cfg))
