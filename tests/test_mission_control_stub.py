from __future__ import annotations

import pytest

try:
    from adhash.mission_control import app as mission_app
except ImportError as exc:  # pragma: no cover - optional dependency
    pytestmark = pytest.mark.skip(reason=f"Mission Control app unavailable: {exc}")


def test_run_mission_control_requires_pyqt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mission_app, "QT_IMPORT_ERROR", ImportError("missing Qt"))
    with pytest.raises(RuntimeError):
        mission_app.run_mission_control([])
