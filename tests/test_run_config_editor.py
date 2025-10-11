from __future__ import annotations

from pathlib import Path

import pytest

from adhash.cli import app


def test_run_config_editor_apply_and_save_preset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()

    base_cfg = app.AppConfig()
    preset_path = preset_dir / "custom.toml"
    preset_path.write_text(app.format_app_config_to_toml(base_cfg), encoding="utf-8")

    inputs: list[str] = [""] * 20

    def fake_input(_: str) -> str:
        return inputs.pop() if inputs else ""

    def fake_print(_: str) -> None:
        return None

    monkeypatch.setitem(app.__dict__, "prompt_for_config", lambda cfg, **_kwargs: cfg)

    result = app.run_config_editor(
        infile=None,
        outfile=str(tmp_path / "out.toml"),
        apply_preset="custom",
        save_preset_name="saved",
        presets_dir=str(preset_dir),
        force=True,
        input_fn=fake_input,
        print_fn=fake_print,
    )

    assert Path(result["outfile"]).exists()
    assert result["apply_preset"] == "custom"
    assert (preset_dir / "saved.toml").exists()
