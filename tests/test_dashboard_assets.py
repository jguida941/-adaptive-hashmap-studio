from pathlib import Path


def test_dashboard_uses_plotly() -> None:
    html = Path("hashmap_cli.py").read_text(encoding="utf-8")
    assert "plotly" in html.lower()
    assert "chart-load" in html
    assert "chart-throughput" in html
    assert "chart-latency" in html
    assert "chart-probe-bar" in html
    assert "chart-heatmap" in html
