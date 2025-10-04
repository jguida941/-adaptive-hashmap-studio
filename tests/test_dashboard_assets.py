
from importlib import resources


def _read_static(name: str) -> str:
    return resources.files("adhash.metrics.static").joinpath(name).read_text(encoding="utf-8")


DASHBOARD_HTML = _read_static("dashboard.html")
DASHBOARD_JS = _read_static("dashboard.js")


def test_dashboard_has_canvas_charts() -> None:
    html = DASHBOARD_HTML
    assert "chart-load" in html
    assert "chart-throughput" in html
    assert "chart-latency" in html
    assert "chart-heatmap" in html

    js_lower = DASHBOARD_JS.lower()
    assert "drawlinechart" in js_lower
    assert "drawheatmap" in js_lower
    assert "chart-tooltip" in js_lower


def test_dashboard_links_static_assets() -> None:
    assert "dashboard.css" in DASHBOARD_HTML
    assert "dashboard.js" in DASHBOARD_HTML
