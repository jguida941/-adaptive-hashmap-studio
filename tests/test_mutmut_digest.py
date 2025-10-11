from collections import Counter

import pytest

try:
    from tools.mutmut_digest import bucketize, parse_mutmut_results
except ModuleNotFoundError:  # pragma: no cover - optional tooling dependency
    pytest.skip("tools.mutmut_digest unavailable", allow_module_level=True)


def test_parse_mutmut_results_collapses_duplicate_statuses() -> None:
    lines = [
        "adhash.metrics.core.foo__mutmut_1: survived",
        "adhash.metrics.core.foo__mutmut_1: survived",
        "adhash.metrics.server.bar__mutmut_9: timeout",
    ]
    status_by_ident = parse_mutmut_results(lines)
    assert status_by_ident["adhash.metrics.core.foo__mutmut_1"]["survived"] == 2
    assert status_by_ident["adhash.metrics.server.bar__mutmut_9"]["timeout"] == 1


def test_totals_are_not_double_counted() -> None:
    lines = [
        "adhash.metrics.core.foo__mutmut_1: survived",
    ]
    status_by_ident = parse_mutmut_results(lines)
    module_counts = bucketize(status_by_ident)

    naive: Counter[str] = Counter()
    for counts in module_counts.values():
        naive.update(counts)
    assert naive["survived"] == 3

    correct: Counter[str] = Counter()
    for counts in status_by_ident.values():
        correct.update(counts)
    assert correct["survived"] == 1
