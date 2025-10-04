from adhash.metrics import DASHBOARD_HTML


def test_dashboard_has_canvas_charts() -> None:
    html = DASHBOARD_HTML
    lowered = html.lower()
    assert "drawlinechart" in lowered
    assert "drawheatmap" in lowered
    assert "chart-load" in html
    assert "chart-throughput" in html
    assert "chart-latency" in html
    assert "chart-heatmap" in html
    assert "chart-tooltip" in html
    assert "IDLE" in html
