from __future__ import annotations

from typing import Any, Iterator


class Draft202012Validator:
    def __init__(self, schema: Any) -> None: ...

    def iter_errors(self, instance: Any) -> Iterator[Any]: ...

    def validate(self, instance: Any) -> None: ...
