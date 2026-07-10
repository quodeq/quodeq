from pathlib import Path

from quodeq_bench.metrics import DimensionMetrics
from quodeq_bench.report import (
    average_reports,
    build_report,
    collect_meta,
    load_report,
    to_markdown,
    write_report,
)


def _report(precision: float, recall: float) -> dict:
    m = DimensionMetrics(total_labels=4, matched_labels=int(recall * 4))
    report = build_report({"model": "m", "provider": "p", "reps": 1}, {"security": m})
    report["metrics"]["security"]["precision"] = precision
    report["metrics"]["security"]["recall"] = recall
    return report


def test_build_and_roundtrip(tmp_path: Path) -> None:
    report = _report(0.8, 0.75)
    path = tmp_path / "report.json"
    write_report(path, report)
    assert load_report(path) == report
    assert report["errored"] is False


def test_average_reports() -> None:
    avg = average_reports([_report(0.8, 0.5), _report(0.6, 1.0)])
    assert avg["metrics"]["security"]["precision"] == 0.7
    assert avg["metrics"]["security"]["recall"] == 0.75
    assert avg["meta"]["model"] == "m"


def test_to_markdown_contains_dimensions() -> None:
    text = to_markdown(_report(0.8, 0.75))
    assert "| security |" in text
    assert "0.8" in text


def test_collect_meta_in_repo() -> None:
    meta = collect_meta(Path.cwd(), "claude", "haiku", 2)
    assert meta["provider"] == "claude"
    assert meta["reps"] == 2
    assert len(meta["quodeq_commit"]) >= 7
    assert len(meta["prompts_hash"]) == 64


def test_prompts_hash_reflects_subdirectory(tmp_path: Path) -> None:
    prompts = tmp_path / "src" / "quodeq" / "data" / "prompts"
    (prompts / "a").mkdir(parents=True)
    (prompts / "a" / "x.md").write_text("same content", encoding="utf-8")
    first = collect_meta(tmp_path, "p", "m", 1)["prompts_hash"]
    (prompts / "b").mkdir()
    (prompts / "a" / "x.md").rename(prompts / "b" / "x.md")
    second = collect_meta(tmp_path, "p", "m", 1)["prompts_hash"]
    assert first != second


def test_average_preserves_integer_counts() -> None:
    avg = average_reports([_report(0.8, 0.5), _report(0.6, 1.0)])
    assert avg["metrics"]["security"]["total_labels"] == 4
    assert isinstance(avg["metrics"]["security"]["total_labels"], int)
