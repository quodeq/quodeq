from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis.manifest_build import count_source_lines


def test_counts_newlines_and_skips_unreadable_and_huge_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x\ny\nz\n", encoding="utf-8")
    (tmp_path / "b.py").write_bytes(b"\xff\xfe" + b"\n" * 5)
    big = tmp_path / "c.py"
    big.write_bytes(b"\n" * (2 * 1024 * 1024 + 1))
    assert count_source_lines(tmp_path, ["a.py", "b.py", "c.py", "missing.py"]) == 8


def test_single_scope_manifest_records_total_lines(tmp_path: Path) -> None:
    from quodeq.analysis.manifest import build_manifest

    (tmp_path / "a.py").write_text("x\ny\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("z\n", encoding="utf-8")
    detection = {"extensions": {".py": "python"}, "skip_dirs": [], "skip_patterns": []}
    manifest = build_manifest(tmp_path, detection)
    assert manifest.total_files == 2
    assert manifest.total_lines == 3


def test_manifest_serialises_the_line_count() -> None:
    from quodeq.analysis.manifest_models import SourceManifest
    from quodeq.analysis.manifest_serialization import manifest_to_dict

    assert manifest_to_dict(SourceManifest(total_lines=42))["source_line_count"] == 42
    assert manifest_to_dict(SourceManifest())["source_line_count"] is None


def test_overlapping_targets_do_not_double_count(tmp_path: Path) -> None:
    from quodeq.analysis.manifest_lines import count_target_lines
    from quodeq.analysis.manifest_models import AnalysisTarget

    (tmp_path / "a.py").write_text("x\ny\n", encoding="utf-8")
    t1 = AnalysisTarget(name="one", language="python", source_files=["a.py"])
    t2 = AnalysisTarget(name="two", language="python", source_files=["a.py"])
    assert count_target_lines(tmp_path, [t1, t2]) == 2


def test_scope_filter_carries_the_count_only_when_it_drops_nothing() -> None:
    from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
    from quodeq.analysis.manifest_scope import filter_manifest_by_scope

    target = AnalysisTarget(
        name="t", language="python", source_files=["pkg/a.py", "other/b.py"], total_files=2,
    )
    manifest = SourceManifest(targets=[target], total_files=2, total_lines=10)
    kept_all = SourceManifest(
        targets=[AnalysisTarget(name="t", language="python", source_files=["pkg/a.py"], total_files=1)],
        total_files=1, total_lines=4,
    )
    assert filter_manifest_by_scope(manifest, "pkg").total_lines is None
    assert filter_manifest_by_scope(kept_all, "pkg").total_lines == 4


def test_line_count_reaches_the_evidence_dict_and_the_report(tmp_path: Path) -> None:
    from quodeq.data.fs.dimension_report.report_assembly import assemble_report_dict
    from quodeq.analysis.run_types import RunConfig
    from quodeq.analysis.manifest_models import SourceManifest
    from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence

    config = RunConfig(src=tmp_path, language="python", manifest=SourceManifest(total_lines=77))
    assert config.source_line_count == 77
    assert RunConfig(src=tmp_path, language="python").source_line_count is None

    jsonl = tmp_path / "e.jsonl"
    jsonl.write_text("", encoding="utf-8")
    evidence = parse_jsonl_to_evidence(jsonl, EvidenceContext(
        language="python", repository="r", date_str="d", source_file_count=3, files_read=1,
        source_line_count=config.source_line_count,
    ))
    assert evidence.source_line_count == 77
    scoring = evidence.to_evidence_dict()
    assert scoring["source_line_count"] == 77
    from quodeq.data.fs.dimension_report.report_assembly import ReportData
    report = assemble_report_dict(ReportData(
        dimension="d", evidence=scoring, top_score=None, top_grade=None,
        principle_rows=[], flat_violations=[], flat_compliance=[], sev_tally={},
    ))
    assert report["sourceLineCount"] == 77


def test_the_line_count_can_be_skipped(tmp_path: Path, monkeypatch) -> None:
    """A caller that only counts files (the estimates endpoint) reads no file for lines."""
    from quodeq.analysis.manifest import build_manifest

    (tmp_path / "a.py").write_text("x\ny\n", encoding="utf-8")
    detection = {"extensions": {".py": "python"}, "skip_dirs": [], "skip_patterns": []}

    def boom(*_a, **_k):
        raise AssertionError("line count ran")

    monkeypatch.setattr("quodeq.analysis.manifest_build.count_source_lines", boom)
    manifest = build_manifest(tmp_path, detection, count_lines=False)
    assert manifest.total_files == 1
    assert manifest.total_lines is None


def test_estimates_build_the_manifest_without_the_line_count(tmp_path: Path, monkeypatch) -> None:
    import quodeq.analysis.estimates as estimates

    seen: list[bool] = []
    real = estimates.build_manifest

    def spy(*args, **kwargs):
        seen.append(kwargs.get("count_lines", True))
        return real(*args, **kwargs)

    monkeypatch.setattr(estimates, "build_manifest", spy)
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x\n", encoding="utf-8")
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "repository_info.json").write_text(json.dumps({"path": str(src)}), encoding="utf-8")
    estimates.project_estimates_payload(project_dir, None, False)
    assert seen == [False]
