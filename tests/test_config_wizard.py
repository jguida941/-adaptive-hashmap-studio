from __future__ import annotations

from pathlib import Path
from typing import Iterator, List

from hashmap_cli import AppConfig, run_config_wizard


def make_input(responses: List[str]) -> Iterator[str]:
    for response in responses:
        yield response
    while True:
        yield ""


def test_config_wizard_generates_toml(tmp_path: Path) -> None:
    responses = [
        "robinhood",  # start backend
        "128",        # initial buckets
        "16",         # groups per bucket
        "128",        # initial capacity
        "4096",       # incremental batch
        "0.75",       # max lf chaining
        "6",          # max group len
        "5.5",        # max avg probe
        "0.2",        # max tombstone ratio
        "250000",     # large map warn
        "y",          # watchdog enabled
        "0.88",       # load factor warn
        "7.5",        # avg probe warn
        "0.3",        # tombstone ratio warn
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
        "",   # default start backend
        "",   # initial buckets
        "",   # groups per bucket
        "",   # initial capacity
        "",   # incremental batch
        "",   # max lf
        "",   # group len
        "",   # max avg probe
        "",   # tombstone ratio
        "",   # large warn
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
