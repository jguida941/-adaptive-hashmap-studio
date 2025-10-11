from __future__ import annotations

import importlib
import runpy
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest


@pytest.fixture()
def shim_modules() -> Iterator[tuple[Any, Any]]:
    """Reload the CLI modules to exercise alias behaviour and restore afterwards."""

    module_names = ("adhash.hashmap_cli", "adhash.cli.app")
    saved = {name: sys.modules[name] for name in module_names if name in sys.modules}
    for name in module_names:
        sys.modules.pop(name, None)
    shim = importlib.import_module("adhash.hashmap_cli")
    target = importlib.import_module("adhash.cli.app")
    try:
        yield shim, target
    finally:
        for name in module_names:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_hashmap_cli_is_direct_alias(
    shim_modules: tuple[object, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    shim, target = shim_modules
    shim_any = cast(Any, shim)
    target_any = cast(Any, target)
    assert shim is target

    # Mutations via one import path should be visible via the other.
    monkeypatch.setattr(shim_any, "_shim_test_flag", 123, raising=False)
    assert hasattr(target_any, "_shim_test_flag")
    assert cast(Any, target_any)._shim_test_flag == 123

    monkeypatch.setattr(target_any, "_shim_test_flag", 456, raising=False)
    assert cast(Any, shim_any)._shim_test_flag == 456


def test_hashmap_cli_exports_target_symbols(shim_modules: tuple[object, object]) -> None:
    shim, target = shim_modules
    exported = getattr(target, "__all__", None)
    if exported is None:
        expected = [name for name in dir(target) if not name.startswith("_")]
    else:
        expected = list(exported)
    assert all(hasattr(shim, name) for name in expected)


def test_shim_dir_reflects_target_attributes(shim_modules: tuple[object, object]) -> None:
    shim, target = shim_modules
    names = dir(shim)
    exported = getattr(target, "__all__", None)
    if exported is None:
        expected = [name for name in dir(target) if not name.startswith("_")]
    else:
        expected = [name for name in exported if not name.startswith("_")]
    for name in expected:
        assert name in names


def test_shim_get_set_and_del_attr(shim_modules: tuple[object, object]) -> None:
    shim, target = shim_modules
    shim_any = cast(Any, shim)
    target_any = cast(Any, target)
    target_any.shim_temp = "seed"
    try:
        assert shim_any.shim_temp == "seed"  # __getattr__
        shim_any.shim_temp = "updated"  # __setattr__
        assert target_any.shim_temp == "updated"
        del shim_any.shim_temp  # __delattr__
        assert not hasattr(target_any, "shim_temp")
    finally:
        if hasattr(target_any, "shim_temp"):
            delattr(target_any, "shim_temp")


def test_assign_meta_clones_metadata() -> None:
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "src" / "hashmap_cli" / "__init__.py"
    namespace = runpy.run_path(str(module_path), run_name="hashmap_cli")
    shim_cls = namespace["_Shim"]
    assign_meta = namespace["_assign_meta"]

    new_shim = shim_cls("hashmap_cli_test")
    assign_meta(new_shim, exports=["foo", "bar"])
    assert new_shim.__all__ == ["foo", "bar"]
    assert new_shim.__package__ == "hashmap_cli"
    assert isinstance(new_shim.__path__, list)


def test_hashmap_cli_fallback_reports_inspected_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    module_names = ("adhash.hashmap_cli", "adhash.cli.app")
    saved = {name: sys.modules[name] for name in module_names if name in sys.modules}
    original_import = importlib.import_module

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "adhash.cli.app":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    monkeypatch.setattr(Path, "exists", lambda _: False)

    for name in module_names:
        sys.modules.pop(name, None)

    with pytest.raises(ImportError) as excinfo:
        importlib.import_module("adhash.hashmap_cli")

    message = str(excinfo.value)
    assert "Unable to locate the `adhash` package" in message
    assert "Searched in:" in message

    for name in module_names:
        sys.modules.pop(name, None)
    sys.modules.update(saved)
