"""Live-progress polling reuses one IncrementalTally per evidence file.

Findings 5531/5532: `_dim_evidence_tally` and `_consolidated_dim_progress`
called `tally_unique_findings` from byte 0 on every poll, so a growing
evidence.jsonl got fully re-parsed on every ~2s tick while a pool ran.
`live_tally` memoizes an `IncrementalTally` per (file, suppression state) so
a poll only reads what was appended since the previous one.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.evidence_tally import tally_unique_findings
from quodeq.services._scan_progress_dims import (
    _LIVE_TALLIES,
    _dim_evidence_tally,
    _suppression_stamp,
)


def _row(p, file, line, t="violation"):
    return json.dumps({"p": p, "file": file, "line": line, "t": t}) + "\n"


def _seed_evidence(run_dir: Path, dim_id: str) -> Path:
    path = run_dir / "evidence" / f"{dim_id}_evidence.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_row("P1", "a.py", 1) + _row("P2", "b.py", 2))
    return path


def _memo_key(path, dim_id, dismissed, deleted, evaluators_dir, compiled_dir):
    return (str(path), (dim_id, _suppression_stamp(dismissed, deleted),
                        str(evaluators_dir), str(compiled_dir)))


def test_dim_progress_polls_reuse_one_incremental_tally_per_file(tmp_path):
    _LIVE_TALLIES.clear()
    run_dir = tmp_path / "run"
    dim_id = "security"
    evaluators_dir = tmp_path / "no_such_evaluators"
    compiled_dir = tmp_path / "no_such_compiled"
    path = _seed_evidence(run_dir, dim_id)
    dismissed, deleted = frozenset(), frozenset()

    first = _dim_evidence_tally(dim_id, run_dir, dismissed, deleted, evaluators_dir, compiled_dir)
    assert first == tally_unique_findings(path)

    with path.open("a") as f:
        f.write(_row("P3", "c.py", 3))

    second = _dim_evidence_tally(dim_id, run_dir, dismissed, deleted, evaluators_dir, compiled_dir)
    assert second == tally_unique_findings(path)

    assert len(_LIVE_TALLIES) == 1
    key = _memo_key(path, dim_id, dismissed, deleted, evaluators_dir, compiled_dir)
    tally = _LIVE_TALLIES.get(key)
    assert tally is not None
    assert tally.offset == path.stat().st_size


def test_a_changed_suppression_state_starts_a_fresh_tally(tmp_path):
    _LIVE_TALLIES.clear()
    run_dir = tmp_path / "run"
    dim_id = "security"
    evaluators_dir = tmp_path / "no_such_evaluators"
    compiled_dir = tmp_path / "no_such_compiled"
    _seed_evidence(run_dir, dim_id)

    _dim_evidence_tally(dim_id, run_dir, frozenset(), frozenset(), evaluators_dir, compiled_dir)
    assert len(_LIVE_TALLIES) == 1

    changed = frozenset({("security", "a.py", 1)})
    _dim_evidence_tally(dim_id, run_dir, changed, frozenset(), evaluators_dir, compiled_dir)
    assert len(_LIVE_TALLIES) == 2
