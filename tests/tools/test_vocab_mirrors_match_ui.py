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
from quodeq.assistant.tools.actions import ACTIONS
from quodeq.core.types.finding_type import FindingType
from quodeq.core.types.project_source import ProjectSource
from quodeq.core.types.provider import Provider
from quodeq.core.types.severity import Severity
from quodeq.llm_bridge import LOCAL_PROVIDERS
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
    ("vocab/frameType.js", "FRAME_TYPE", FrameType),
    ("vocab/scopeGateRule.js", "SCOPE_GATE_RULE", ScopeGateRule),
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
    covered = (
        {rel for rel, _, _ in _MIRRORS if rel.startswith("vocab/")}
        | _SPECIAL_VOCAB_MODULES
        | _UI_ONLY_VOCAB_MODULES
    )
    present = {f"vocab/{p.name}" for p in _VOCAB_DIR.glob("*.js") if not p.name.endswith(".test.js")}
    assert present == covered


_PROVIDER_JS = _UI_SRC / "vocab" / "provider.js"
# vocab/ modules with a Python backend concept, but in a mirror shape _MIRRORS
# cannot express (a subset, or a Set rather than a StrEnum); each has its own
# test below.
_SPECIAL_VOCAB_MODULES = {"vocab/provider.js", "vocab/logStreamStatus.js", "vocab/actionType.js"}

# vocab/ modules with no Python backend concept at all: purely client-side UI
# vocab (a DOM event/key spelling, or a presentational/routing choice this
# repo never sends over the wire to or from Python). A member-pinning test is
# optional here; vocab.test.js already pins some of these (KEY, NAV_TAB) --
# don't duplicate what it covers.
_UI_ONLY_VOCAB_MODULES = {
    "vocab/keyboard.js",       # KeyboardEvent .key/.code spellings (DOM spec, not Python)
    "vocab/navTab.js",         # nav-stack page ids: purely client-side routing
    "vocab/theme.js",          # theme mode/family: purely presentational choice
    "vocab/pointerEvent.js",   # pointer-drag DOM event names (DOM spec, not Python)
    "vocab/sortDirection.js",  # sort-toggle direction: purely client-side UI concept
    "vocab/dialogVariant.js",  # dialog action-button style: purely presentational choice
}


def test_ui_log_stream_status_has_expected_members():
    """LOG_STREAM_STATUS has no Python enum (the SSE stream is UI-only): pin
    its members directly instead of comparing against an enum."""
    assert _js_object(_UI_SRC / "vocab" / "logStreamStatus.js", "LOG_STREAM_STATUS") == {
        "IDLE": "idle", "STREAMING": "streaming", "DONE": "done", "ERROR": "error",
    }


def test_ui_action_type_mirrors_a_subset_of_the_backend_action_types():
    """ACTION_TYPE names only the two action types the UI branches on by name
    (assistantAppBridge.js, verifiedFindingsContext.jsx, ActionPreviewCard.jsx);
    create_standard has no such UI-side effect, so it's absent by design. Not a
    full mirror (and ACTIONS is dict keys, not a StrEnum), so not in _MIRRORS --
    but every value present must still match a real assistant/tools/actions.py
    ACTIONS key exactly."""
    ui = _js_object(_UI_SRC / "vocab" / "actionType.js", "ACTION_TYPE")
    assert ui == {"DISMISS_FINDING": "dismiss_finding", "VERIFY_FINDING": "verify_finding"}
    assert set(ui.values()) <= set(ACTIONS)


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
