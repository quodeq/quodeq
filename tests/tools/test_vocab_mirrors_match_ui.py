"""Every closed vocabulary shared with Python is spelled twice: the Python
StrEnum and its UI mirror (under ui/src/vocab/*.js, or in the feature module
that owns it, like PUBLISH_STATE in features/dashboard/dashboardVocab.js).
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
from quodeq.analysis.mcp.scope_gate_rules import ScopeGateRule
from quodeq.assistant.frame_type import FrameType
from quodeq.core.types.finding_type import FindingType
from quodeq.core.types.project_source import ProjectSource
from quodeq.core.types.provider import Provider
from quodeq.core.types.severity import Severity
from quodeq.llm_bridge import LOCAL_PROVIDERS
from quodeq.services.shared_publish import PublishState
from quodeq.services.grade_formula_job import RescoreState

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
    ("vocab/frameType.js", "FRAME_TYPE", FrameType),
    ("vocab/scopeGateRule.js", "SCOPE_GATE_RULE", ScopeGateRule),
    ("vocab/rescoreState.js", "RESCORE_STATE", RescoreState),
    ("features/dashboard/dashboardVocab.js", "PUBLISH_STATE", PublishState),
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
    covered = {rel for rel, _, _ in _MIRRORS if rel.startswith("vocab/")} | _SPECIAL_VOCAB_MODULES
    present = {f"vocab/{p.name}" for p in _VOCAB_DIR.glob("*.js") if not p.name.endswith(".test.js")}
    assert present == covered


_PROVIDER_JS = _UI_SRC / "vocab" / "provider.js"
# vocab/ modules with a mirror shape _MIRRORS cannot express; each has its own test below.
_SPECIAL_VOCAB_MODULES = {"vocab/provider.js", "vocab/logStreamStatus.js"}


def test_ui_log_stream_status_has_expected_members():
    """LOG_STREAM_STATUS has no Python enum (the SSE stream is UI-only): pin
    its members directly instead of comparing against an enum."""
    assert _js_object(_UI_SRC / "vocab" / "logStreamStatus.js", "LOG_STREAM_STATUS") == {
        "IDLE": "idle", "STREAMING": "streaming", "DONE": "done", "ERROR": "error",
    }


def _js_provider_set(name: str, members: dict[str, str], known: dict[str, set[str]]) -> set[str]:
    """The values of ``export const <name> = new Set([PROVIDER.X, ...OTHER])`` in vocab/provider.js."""
    text = _PROVIDER_JS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name}\s*=\s*new Set\(\[(.*?)\]\)", text, re.DOTALL)
    assert match, f"{name} not found in {_PROVIDER_JS}"
    out: set[str] = set()
    for member, spread in re.findall(r"PROVIDER\.(\w+)|\.\.\.(\w+)", match.group(1)):
        out |= {members[member]} if member else known[spread]
    return out


def test_ui_provider_mirror_is_python_provider_plus_omlx():
    ui = _js_object(_PROVIDER_JS, "PROVIDER")
    assert ui.pop("OMLX") == "omlx"
    assert ui == {m.name: m.value for m in Provider}


def test_ui_provider_sets_match_the_backend_gate():
    members = _js_object(_PROVIDER_JS, "PROVIDER")
    local = _js_provider_set("LOCAL_API_PROVIDERS", members, {})
    assert local == set(LOCAL_PROVIDERS)
    web = _js_provider_set("WEB_TOOL_PROVIDERS", members, {"LOCAL_API_PROVIDERS": local})
    assert web == set(LOCAL_PROVIDERS) | {Provider.CLAUDE}
