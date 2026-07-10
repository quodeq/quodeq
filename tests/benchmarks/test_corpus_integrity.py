from pathlib import Path

import pytest

from quodeq_bench.models import load_truth

_CORPUS = Path(__file__).resolve().parents[2] / "benchmarks" / "corpus" / "synthetic"


def _cases() -> list[Path]:
    return sorted(p.parent for p in _CORPUS.glob("*/truth.json"))


def test_corpus_is_not_empty() -> None:
    assert _cases(), f"no synthetic cases under {_CORPUS}"


@pytest.mark.parametrize("case_dir", _cases(), ids=lambda p: p.name)
def test_case_integrity(case_dir: Path) -> None:
    truth = load_truth(case_dir)
    for clean in truth.clean_files:
        assert (case_dir / clean).is_file(), f"clean file missing: {clean}"
    for label in truth.labels:
        target = case_dir / label.file
        assert target.is_file(), f"label file missing: {label.file}"
        lines = target.read_text(encoding="utf-8").splitlines()
        assert label.line <= len(lines), (
            f"{label.file}:{label.line} beyond EOF ({len(lines)} lines)"
        )
        if label.anchor:
            assert label.anchor in lines[label.line - 1], (
                f"{label.file}:{label.line} anchor {label.anchor!r} not on line: "
                f"{lines[label.line - 1]!r}"
            )
