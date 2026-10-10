"""Type checks on the fields of a findings mutation body.

Missing fields stay the route's MISSING_PARAM concern; this only rejects
present values of the wrong type, so list/dict/number payloads get a 400 at
the API boundary instead of crashing in the persistence layer.
"""
from __future__ import annotations

from typing import Any


def invalid_body_fields(
    body: dict[str, Any],
    str_fields: tuple[str, ...],
    int_fields: tuple[str, ...] = (),
) -> str | None:
    """Return a message naming mistyped body fields, or None when types are fine.

    Missing fields stay the caller's MISSING_PARAM concern; this only rejects
    present values of the wrong type (str fields must be str, int fields must
    be a non-bool int) so list/dict/number payloads get a 400 at the API
    boundary instead of crashing in the persistence layer.
    """
    bad: list[str] = []
    for name in str_fields:
        value = body.get(name)
        if value is not None and not isinstance(value, str):
            bad.append(f"{name} (must be a string)")
    for name in int_fields:
        value = body.get(name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            bad.append(f"{name} (must be an integer)")
    if bad:
        return f"invalid fields: {', '.join(bad)}"
    return None
