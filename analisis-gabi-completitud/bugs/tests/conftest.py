import sys
from pathlib import Path

# Permite `from parse import ...` y `from detectores import ...` desde los tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
