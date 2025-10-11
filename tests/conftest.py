import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure PyQt widgets render without an attached display (headless mutation runs).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if SRC.exists():
    sys.path.insert(0, str(SRC))

# Register shared Hypothesis profiles for deterministic CI runs and fast local loops.
from tests.util import hypothesis_profiles  # noqa: E402,F401  pylint: disable=unused-import

MUTATION_MODE = os.getenv("MUTATION_TESTS") == "1"


@pytest.fixture(name="_monkeypatch")
def _monkeypatch_fixture(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Backward-compatible alias for code still expecting `_monkeypatch`."""

    return monkeypatch


@pytest.fixture(name="_caplog")
def _caplog_fixture(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """Alias for legacy `_caplog` fixture references."""

    return caplog


@pytest.fixture(name="_qt_app")
def _qt_app_fixture(qt_app: Any) -> Any:
    """Alias for legacy `_qt_app` fixture references provided by pytest-qt."""

    return qt_app


def pytest_configure(config: pytest.Config) -> None:
    """Ensure custom marks remain registered even when pytest.ini isn't picked up."""
    config.addinivalue_line("markers", "qt: Qt / pyqtgraph dependent tests")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    if not MUTATION_MODE:
        return

    skip_mutation = pytest.mark.skip(reason="Skipping slow/GUI tests during mutation run")
    for item in items:
        module = getattr(item, "module", None)
        module_name = getattr(module, "__name__", "")
        if module_name.endswith("test_batch_runner"):
            item.add_marker(skip_mutation)
        if module_name.endswith("test_mission_control_widgets_qt"):
            item.add_marker(skip_mutation)
