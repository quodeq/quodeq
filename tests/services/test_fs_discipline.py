"""Discipline inference reads evidence JSON that may be any shape."""
from __future__ import annotations

from pathlib import Path

from quodeq.services.fs_projects import infer_discipline
from quodeq.shared.constants import EVIDENCE_DIRNAME


def _evidence_file(reports_root: Path) -> Path:
    evidence_dir = reports_root / "proj" / "20260101" / EVIDENCE_DIRNAME
    evidence_dir.mkdir(parents=True)
    return evidence_dir / "x_evidence.json"


def test_infer_discipline_handles_non_object_and_bad_bytes(tmp_path: Path) -> None:
    p = _evidence_file(tmp_path)
    p.write_text("[1]")
    assert infer_discipline(tmp_path, "proj") is None
    p.write_bytes(b"\xff")
    assert infer_discipline(tmp_path, "proj") is None
    p.write_text('{"discipline": "python"}')
    assert infer_discipline(tmp_path, "proj") == "python"
