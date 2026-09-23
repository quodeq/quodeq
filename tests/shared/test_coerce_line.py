"""One public ``coerce_line`` instead of three private copies.

``_coerce_line`` lived in ``services/suppression_keys.py`` (re-exported by
``services/suppression.py``), was duplicated verbatim in
``assistant/tools/_read_tools_violations.py``, and was imported as a private
symbol across packages by ``ci/github_render.py``. The single implementation
now lives in ``shared/serialization.py``; these tests pin its semantics (they
are the union of what the three former sites relied on).
"""
from __future__ import annotations

import pytest

from quodeq.shared.serialization import coerce_line


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (12, 12),
        ("12", 12),          # Finding.line may arrive as a string
        (0, 0),
        (None, 0),           # absent line: keys on 0, matching stored dismiss keys
        ("", 0),
        ("twelve", 0),
        ("5.5", 0),          # int("5.5") is a ValueError, not a truncation
        (7.9, 7),            # int() truncates a float, as the old copies did
        (True, 1),           # bool is an int subclass; unchanged behavior
    ],
)
def test_coerce_line(value, expected):
    assert coerce_line(value) == expected


def test_former_call_sites_use_the_shared_implementation():
    from quodeq.assistant.tools import _read_tools_violations
    from quodeq.ci import github_render
    from quodeq.services import suppression, suppression_keys

    # No private copies left anywhere.
    assert not hasattr(_read_tools_violations, "_coerce_line")
    assert not hasattr(suppression, "_coerce_line")
    assert not hasattr(suppression_keys, "_coerce_line")
    # The CI renderer resolves a string line through the shared helper.
    assert github_render.violation_to_comment({"line": "12", "file": "a.py"})["line"] == 12
