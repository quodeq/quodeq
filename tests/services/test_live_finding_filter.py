"""LiveFindingFilter: the SSE feed sees exactly what the heartbeat counts as a violation.

The run event log holds every judgment the model made, compliance included.
Before this filter existed the stream forwarded all of them as ``finding``
frames, so a dimension with 42 violations showed 417 rows in the live feed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.config.paths import default_paths
from quodeq.core.events.models import Judgment
from quodeq.services.dismissed import dismiss_finding
from quodeq.services.live_finding_filter import LiveFindingFilter


def _judgment(**overrides) -> Judgment:
    base = dict(
        practice_id="P1", verdict="violation", dimension="dim",
        file="a.py", line=1, reason="r", severity="major",
    )
    base.update(overrides)
    return Judgment(**base)


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    # Layout is <project>/<run>: suppression state is project-scoped.
    run = tmp_path / "proj" / "run-1"
    run.mkdir(parents=True)
    return run


def test_a_violation_is_admitted(run_dir: Path):
    flt = LiveFindingFilter(run_dir)
    assert flt.admits(_judgment()) is True


def test_a_compliance_judgment_is_not_a_finding(run_dir: Path):
    flt = LiveFindingFilter(run_dir)
    assert flt.admits(_judgment(verdict="compliance")) is False


def test_the_same_finding_reported_twice_is_admitted_once(run_dir: Path):
    # Two agents can report one finding; the heartbeat folds the second away.
    flt = LiveFindingFilter(run_dir)
    assert flt.admits(_judgment()) is True
    assert flt.admits(_judgment()) is False
    # A different line is a different finding.
    assert flt.admits(_judgment(line=2)) is True


def test_dedup_is_per_dimension(run_dir: Path):
    # Same principle, file and line under two dimensions is two findings.
    flt = LiveFindingFilter(run_dir)
    assert flt.admits(_judgment(dimension="alpha")) is True
    assert flt.admits(_judgment(dimension="beta")) is True
    assert flt.admits(_judgment(dimension="alpha")) is False


def test_a_dismissed_violation_is_not_admitted(run_dir: Path):
    dismiss_finding(run_dir.parent, {"req": "R1", "file": "a.py", "line": 1})
    flt = LiveFindingFilter(run_dir)
    assert flt.admits(_judgment(req="R1")) is False
    # The identity is (req, file, line): another line of the same file still shows.
    assert flt.admits(_judgment(req="R1", line=9)) is True


def test_refresh_picks_up_a_dismissal_that_landed_mid_run(run_dir: Path):
    flt = LiveFindingFilter(run_dir)
    flt.refresh()
    dismiss_finding(run_dir.parent, {"req": "R1", "file": "a.py", "line": 1})
    # Not refreshed yet: the old matcher still admits it.
    assert flt.admits(_judgment(req="R1", line=1)) is True
    flt.refresh()
    assert flt.admits(_judgment(req="R1", file="b.py", line=1)) is True
    dismiss_finding(run_dir.parent, {"req": "R2", "file": "c.py", "line": 3})
    flt.refresh()
    assert flt.admits(_judgment(req="R2", file="c.py", line=3)) is False


def test_a_principle_outside_the_standard_is_quarantined(run_dir: Path):
    compiled = default_paths().standards_dir / "compiled"
    flt = LiveFindingFilter(run_dir, compiled_dir=compiled, evaluators_dir=None)
    assert flt.admits(_judgment(dimension="reliability", practice_id="Not A Principle")) is False
    assert flt.admits(_judgment(dimension="reliability", practice_id="Fault Tolerance")) is True


def test_a_carried_forward_violation_is_still_admitted(run_dir: Path):
    # The client decides whether to hide replayed findings; the server only
    # decides whether a judgment is a finding at all.
    flt = LiveFindingFilter(run_dir)
    assert flt.admits(_judgment(carried_forward=True)) is True


def test_refresh_survives_an_unreadable_suppression_store(run_dir: Path, caplog):
    # A corrupt actions.jsonl must not take the stream down: counts stay raw,
    # the same fallback the heartbeat uses.
    (run_dir.parent / "actions.jsonl").write_text("{not json\n")
    flt = LiveFindingFilter(run_dir)
    flt.refresh()
    assert flt.admits(_judgment()) is True
