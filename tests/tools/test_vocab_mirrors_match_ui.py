"""Every closed vocabulary is spelled twice: the Python StrEnum and its UI
mirror under ui/src/vocab/*.js (plus PUBLISH_STATE in usePublishPolling.js).
The UI's own node test only pins literals, so a value renamed on one side
alone would pass both suites. This reads the JS objects and compares them
member for member with the enums.
"""
from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

import pytest

from quodeq.core.run.dimensions import DimState
from quodeq.core.run.exit_reason import ExitReason
from quodeq.core.run.job_status import JobStatus
from quodeq.core.run.state import RunState
from quodeq.core.scoring.constants import Grade
from quodeq.core.types.finding_type import FindingType
from quodeq.core.types.project_source import ProjectSource
from quodeq.core.types.severity import Severity
from quodeq.services.shared_publish import PublishState

_UI_SRC = Path(__file__).resolve().parents[2] / "src" / "quodeq" / "ui" / "src"
_VOCAB_DIR = _UI_SRC / "vocab"

# (file under ui/src, exported const, Python enum)
_MIRRORS = [
    ("vocab/runState.js", "RUN_STATE", RunState),
    ("vocab/jobStatus.js", "JOB_STATUS", JobStatus),
    ("vocab/exitReason.js", "EXIT_REASON", ExitReason),
    ("vocab/severity.js", "SEVERITY", Severity),
    ("vocab/grade.js", "GRADE", Grade),
    ("vocab/dimState.js", "DIM_STATE", DimState),
    ("vocab/findingType.js", "FINDING_TYPE", FindingType),
    ("vocab/projectSource.js", "PROJECT_SOURCE", ProjectSource),
    ("features/dashboard/hooks/usePublishPolling.js", "PUBLISH_STATE", PublishState),
]

_PAIR = re.compile(r"(\w+)\s*:\s*'([^']*)'")


def _js_object(path: Path, name: str) -> dict[str, str]:
    """The ``KEY: 'value'`` pairs of ``export const <name> = Object.freeze({...})``."""
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"export const {name}\s*=\s*Object\.freeze\(\{{(.*?)\}}\)", text, re.DOTALL)
    assert match, f"{name} not found in {path}"
    return dict(_PAIR.findall(match.group(1)))


@pytest.mark.parametrize(("rel", "name", "enum"), _MIRRORS, ids=[m[1] for m in _MIRRORS])
def test_ui_mirror_matches_python_enum(rel: str, name: str, enum: type[StrEnum]):
    assert _js_object(_UI_SRC / rel, name) == {m.name: m.value for m in enum}


def test_every_vocab_module_is_covered():
    covered = {rel for rel, _, _ in _MIRRORS if rel.startswith("vocab/")}
    present = {f"vocab/{p.name}" for p in _VOCAB_DIR.glob("*.js") if not p.name.endswith(".test.js")}
    assert present == covered
