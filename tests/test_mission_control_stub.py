from __future__ import annotations

import pytest

from adhash.mission_control import app as mission_app


def test_run_mission_control_requires_pyqt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mission_app, "_QT_IMPORT_ERROR", ImportError("missing Qt"))
    with pytest.raises(RuntimeError):
        mission_app.run_mission_control([])
