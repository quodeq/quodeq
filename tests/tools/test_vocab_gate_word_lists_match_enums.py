"""The Python vocabulary gate's word lists must pin their enum's own values.

tools/check_vocab_literals.py's VOCABULARIES is a hand-written word set per
vocabulary, kept separate from the StrEnum it flags bare literals of so the
gate itself never has to import application code. A word added to (or
dropped from) an enum without updating VOCABULARIES would leave the gate
silently wrong -- either blind to a new value or flagging a value that no
longer exists. This pins every VOCABULARIES entry to its enum's own
``{member.value for member in Enum}``.

RunState is a deliberate exception: VOCABULARIES["RunState"] carries legacy
spellings (``complete``, ``in_progress``, ``canceled``, ...) that
``parse_run_state`` still reads from old status.json files but that are not
current RunState members, so it is a superset there rather than an equality.
"""
from __future__ import annotations

import check_vocab_literals

from quodeq.core.run.dimensions import DimState
from quodeq.core.run.exit_reason import ExitReason
from quodeq.core.run.job_status import JobStatus
from quodeq.core.run.state import RunState
from quodeq.core.scoring.constants import Grade
from quodeq.core.types.finding_type import FindingType
from quodeq.core.types.provider import Provider
from quodeq.core.types.severity import Severity
from quodeq.analysis.mcp.schemas import FileDoneStatus

# Every VOCABULARIES entry's enum, by name. RunState is checked separately
# (subset, not equality) below.
_ENUMS_BY_EQUALITY = {
    "JobStatus": JobStatus,
    "ExitReason": ExitReason,
    "Severity": Severity,
    "Grade": Grade,
    "FileDoneStatus": FileDoneStatus,
    "DimState": DimState,
    "Provider": Provider,
    "FindingType": FindingType,
}


def _values(enum_cls) -> frozenset[str]:
    return frozenset(member.value for member in enum_cls)


def test_every_non_runstate_word_list_equals_its_enum_values():
    for name, enum_cls in _ENUMS_BY_EQUALITY.items():
        assert check_vocab_literals.VOCABULARIES[name] == _values(enum_cls), name


def test_runstate_word_list_is_a_superset_of_runstate_values():
    assert _values(RunState) <= check_vocab_literals.VOCABULARIES["RunState"]


def test_every_vocabularies_key_is_covered():
    covered = set(_ENUMS_BY_EQUALITY) | {"RunState"}
    assert set(check_vocab_literals.VOCABULARIES) == covered
