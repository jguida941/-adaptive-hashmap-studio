"""Compatibility shim preserving the legacy ``hashmap_cli`` import path."""

from __future__ import annotations

import importlib
import sys

_impl = importlib.import_module("adhash.hashmap_cli")

# Replace this module entry with the real implementation so attribute access,
# mutation, and module-level globals behave exactly as before the relocation.
sys.modules[__name__] = _impl
