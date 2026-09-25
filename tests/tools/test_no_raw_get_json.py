"""Routes read JSON bodies only through the api.helpers guards.

A raw ``request.get_json(...) or {}`` hands a list or scalar body to ``.get``
and answers an HTML 500. The guards answer a coded 400 instead.
"""
from __future__ import annotations

from pathlib import Path

_API = Path(__file__).resolve().parents[2] / "src" / "quodeq" / "api"
# The guards themselves, and llm_bridge's json_body (already guarded).
_ALLOWED = {"helpers.py", "_llm_bridge_validation.py"}


def test_no_raw_get_json_outside_the_guards() -> None:
    offenders = [
        f"{path.relative_to(_API)}:{n}"
        for path in sorted(_API.rglob("*.py"))
        if path.name not in _ALLOWED
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "get_json(" in line
    ]
    assert not offenders, "use optional_json_object_or_error / json_object_or_error: " + ", ".join(offenders)
