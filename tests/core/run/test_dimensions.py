"""DimState serialization and the per-dimension transition table."""
import json

import pytest

from quodeq.core.run.dimensions import DimState, IllegalDimTransitionError, validate_dim_transition


@pytest.mark.parametrize("member", list(DimState))
def test_members_serialize_as_their_string(member):
    assert json.dumps(member) == json.dumps(member.value)
    assert member == member.value


def test_str_and_fstring_render_the_plain_value():
    """DimState is enum.StrEnum, not a bare (str, enum.Enum) mixin: str()/
    f-strings must render "done", not "DimState.DONE"."""
    assert f"{DimState.DONE}" == "done"
    assert str(DimState.DONE) == "done"


def test_pending_may_advance_to_running_or_incomplete():
    validate_dim_transition("security", DimState.PENDING, DimState.RUNNING)
    validate_dim_transition("security", DimState.PENDING, DimState.INCOMPLETE)


def test_terminal_states_accept_no_further_transitions():
    for prev in (DimState.DONE, DimState.INCOMPLETE):
        with pytest.raises(IllegalDimTransitionError):
            validate_dim_transition("security", prev, DimState.RUNNING)
