"""RunState serialization, legacy-spelling parsing and the active/terminal split."""
import json

import pytest

from quodeq.core.run.state import ACTIVE_STATES, TERMINAL_STATES, RunState, parse_run_state


@pytest.mark.parametrize("member", list(RunState))
def test_members_serialize_as_their_string(member):
    assert json.dumps(member) == json.dumps(member.value)
    assert member == member.value


def test_str_and_fstring_render_the_plain_value():
    """RunState is enum.StrEnum, not a bare (str, enum.Enum) mixin: str()/
    f-strings must render "done", not "RunState.DONE"."""
    assert f"{RunState.DONE}" == "done"
    assert str(RunState.DONE) == "done"


@pytest.mark.parametrize("raw,expected", [
    ("done", RunState.DONE), ("complete", RunState.DONE), ("completed", RunState.DONE),
    ("finished", RunState.DONE), ("running", RunState.RUNNING), ("in_progress", RunState.RUNNING),
    ("pending", RunState.PENDING), ("finalizing", RunState.FINALIZING),
    ("cancelled", RunState.CANCELLED), ("canceled", RunState.CANCELLED),
    ("failed", RunState.FAILED), ("error", RunState.FAILED), ("lost", RunState.FAILED),
    (" Done ", RunState.DONE),
])
def test_parse_run_state_accepts_legacy_spellings(raw, expected):
    assert parse_run_state(raw) is expected


@pytest.mark.parametrize("raw", ["", None, "bogus"])
def test_parse_run_state_rejects_unknown(raw):
    with pytest.raises(ValueError):
        parse_run_state(raw)


def test_active_and_terminal_partition_the_enum():
    assert ACTIVE_STATES | TERMINAL_STATES == frozenset(RunState)
    assert not (ACTIVE_STATES & TERMINAL_STATES)
