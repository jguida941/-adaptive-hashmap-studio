import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if SRC.exists():
    sys.path.insert(0, str(SRC))

# Register shared Hypothesis profiles for deterministic CI runs and fast local loops.
from tests.util import hypothesis_profiles  # noqa: F401  pylint: disable=unused-import
