from pathlib import Path

from codecompass.evaluate.lib.prescan import run_prescan_metrics


def test_prescan_returns_summary(tmp_path: Path):
    (tmp_path / "a.py").write_text("print('hi')\n")
    summary = run_prescan_metrics(str(tmp_path), "frontend_react")
    assert "Files:" in summary
    assert "Lines:" in summary
