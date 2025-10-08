from __future__ import annotations

from pathlib import Path
from typing import Iterator, List

from adhash.config import AppConfig
from adhash.hashmap_cli import run_config_editor, run_config_wizard


def make_input(responses: List[str]) -> Iterator[str]:
    for response in responses:
        yield response
    while True:
        yield ""


def test_config_wizard_generates_toml(tmp_path: Path) -> None:
    responses = [
        "robinhood",  # start backend
        "128",  # initial buckets
        "16",  # groups per bucket
        "128",  # initial capacity
        "4096",  # incremental batch
        "0.75",  # max lf chaining
        "6",  # max group len
        "5.5",  # max avg probe
        "0.2",  # max tombstone ratio
        "250000",  # large map warn
        "y",  # watchdog enabled
        "0.88",  # load factor warn
        "7.5",  # avg probe warn
        "0.3",  # tombstone ratio warn
    ]
    iterator = make_input(responses)
    path = tmp_path / "custom.toml"

    run_config_wizard(str(path), input_fn=lambda prompt: next(iterator), print_fn=lambda _: None)

    text = path.read_text(encoding="utf-8")
    assert 'start_backend = "robinhood"' in text
    assert "initial_buckets = 128" in text
    assert "incremental_batch = 4096" in text
    assert "max_lf_chaining = 0.75" in text
    assert "enabled = true" in text
    assert "load_factor_warn = 0.88" in text

    cfg = AppConfig.load(path)
    assert cfg.adaptive.start_backend == "robinhood"
    assert cfg.watchdog.enabled is True


def test_config_wizard_allows_none_thresholds(tmp_path: Path) -> None:
    responses = [
        "",  # default start backend
        "",  # initial buckets
        "",  # groups per bucket
        "",  # initial capacity
        "",  # incremental batch
        "",  # max lf
        "",  # group len
        "",  # max avg probe
        "",  # tombstone ratio
        "",  # large warn
        "n",  # watchdog enabled? false
        "none",
        "none",
        "none",
    ]
    iterator = make_input(responses)
    path = tmp_path / "defaults.toml"
    run_config_wizard(str(path), input_fn=lambda prompt: next(iterator), print_fn=lambda _: None)

    cfg = AppConfig.load(path)
    assert cfg.watchdog.enabled is False
    assert cfg.watchdog.load_factor_warn is None
    assert cfg.watchdog.avg_probe_warn is None
    assert cfg.watchdog.tombstone_ratio_warn is None


def test_config_editor_loads_existing_config(tmp_path: Path) -> None:
    existing = tmp_path / "existing.toml"
    existing.write_text(
        """
[adaptive]
start_backend = \"chaining\"
initial_buckets = 64
groups_per_bucket = 8
initial_capacity_rh = 64
incremental_batch = 2048
max_lf_chaining = 0.82
max_group_len = 8
max_avg_probe_robinhood = 6.0
max_tombstone_ratio = 0.25
large_map_warn_threshold = 1000000

[watchdog]
enabled = true
load_factor_warn = 0.9
avg_probe_warn = 8.0
tombstone_ratio_warn = 0.35
""".strip()
        + "\n",
        encoding="utf-8",
    )

    responses = [
        "",  # start backend
        "",  # initial buckets
        "",  # groups per bucket
        "",  # initial capacity
        "",  # incremental batch
        "0.9",  # max load factor updated
        "",  # max group len
        "",  # max avg probe
        "",  # max tombstone ratio
        "",  # large map warn
        "n",  # disable watchdog
        "",  # load factor warn (ignored)
        "none",  # avg probe warn disabled
        "0.40",  # tombstone ratio warn adjusted
    ]
    iterator = make_input(responses)
    output_path = tmp_path / "edited.toml"

    run_config_editor(
        str(existing),
        str(output_path),
        input_fn=lambda prompt: next(iterator),
        print_fn=lambda _: None,
    )

    cfg = AppConfig.load(output_path)
    assert abs(cfg.adaptive.max_lf_chaining - 0.9) < 1e-9
    assert cfg.watchdog.enabled is False
    assert cfg.watchdog.avg_probe_warn is None
    assert cfg.watchdog.tombstone_ratio_warn is not None
    assert abs(cfg.watchdog.tombstone_ratio_warn - 0.4) < 1e-9


def test_config_editor_can_save_preset(tmp_path: Path) -> None:
    preset_dir = tmp_path / "presets"
    output_path = tmp_path / "cfg.toml"
    iterator = make_input([""] * 16)

    result = run_config_editor(
        None,
        str(output_path),
        save_preset_name="baseline",
        presets_dir=str(preset_dir),
        force=True,
        input_fn=lambda prompt: next(iterator),
        print_fn=lambda _: None,
    )

    preset_path = preset_dir / "baseline.toml"
    assert preset_path.exists()
    assert result["preset"] == str(preset_path)
