"""Ningún test escribe los archivos versionados del tablero.

Desde que `build.py` mapea solo los estudios nuevos (`auto_map`), correr la suite podía escribir
en el questions.json real con filas de prueba. Cada test trabaja sobre una copia temporal.
"""
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sources_brand_lift as BL
import sources_social as SOCIAL


@pytest.fixture(autouse=True)
def questions_temporal(tmp_path, monkeypatch):
    copia = tmp_path / "questions.json"
    shutil.copy(BL.QUESTIONS, copia)
    monkeypatch.setattr(BL, "QUESTIONS", str(copia))
    return copia


@pytest.fixture(autouse=True)
def sin_red_ni_cache_social(tmp_path, monkeypatch):
    """Sin tokens de Meta, ninguna fuente puede llamar a la API real, y el caché de seguidores
    apunta a un archivo temporal vacío."""
    for v in ("META_SYSTEM_USER_TOKEN", "META_PCOM_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(SOCIAL, "CACHE", str(tmp_path / "social_cache.json"))
