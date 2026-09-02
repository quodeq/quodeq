"""Low-level text/JSON read helpers with centralized encoding.

These live in core (stdlib-only, no outward imports) so domain modules like
the evidence parser and standards loader can use them without reaching into
``shared/``. ``shared/_io.py`` re-exports them for the rest of the codebase.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import IO, Any

_logger = logging.getLogger(__name__)

TEXT_ENCODING = "utf-8"
"""Standard text encoding used across the codebase for file I/O."""


def open_text(path: str | Path, mode: str = "r") -> IO[str]:
    """Open a text file with the standard encoding. Use as a context manager."""
    return open(path, mode, encoding=TEXT_ENCODING)


def read_json(path: Path) -> dict[str, Any]:
    """Read and parse a JSON object file, returning the parsed dict.

    Enforces the ``-> dict`` contract: a valid-JSON-but-non-object payload (a
    top-level list, string, number, or null) raises ``ValueError`` — the same
    failure mode as a read/parse error. This shuts down the recurring crash
    class where a caller does ``read_json(p).get(...)`` and a hand-edited or
    malformed file that is valid JSON but not an object raises an unhandled
    ``AttributeError`` deep in the caller. Callers that load top-level arrays
    must use a plain ``json.loads`` (or ``default_read_json``), not this helper.
    """
    try:
        data = json.loads(path.read_text(encoding=TEXT_ENCODING))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object in {path}, got {type(data).__name__}"
        )
    return data


def validate_path_segment(*segments: str) -> None:
    """Raise ValueError if any segment contains path traversal or separator characters."""
    for seg in segments:
        if ".." in seg or "/" in seg or "\\" in seg or "\0" in seg:
            raise ValueError(
                f"Invalid path segment: {seg!r}. "
                f"Use only alphanumeric characters, hyphens, underscores, and dots."
            )


def _match_child_entry(entry: os.DirEntry, root: str | Path, name: str) -> str | None:
    """Given a scandir *entry* whose name already matches *name*, return its
    path if it is a real directory, else None (including the symlinked-dir
    case, which logs a warning before returning None)."""
    if entry.is_dir(follow_symlinks=False):
        return entry.path
    if entry.is_symlink() and entry.is_dir():
        # The exact case a user hits after relocating a data dir
        # and leaving a symlink behind: the name they asked for is
        # right there in the listing, but resolution refuses it.
        # Without this line the refusal is indistinguishable from
        # "no such project/run" — the UI just renders empty.
        _logger.warning(
            "Not following symlinked directory %s -> %s: symlinks "
            "are excluded from path resolution by policy. Replace "
            "the symlink with a real directory (or move the data "
            "back) to make %r visible again.",
            os.path.join(str(root), name),
            os.path.realpath(entry.path),
            name,
        )
    return None


def resolve_child_dir(root: str | Path, name: str) -> str | None:
    """Return the child directory of *root* called *name*, or None if absent.

    The returned path comes out of the directory listing; *name* is only ever
    compared against entries that already exist, never concatenated onto
    *root*. That is the entire point. A traversal segment, an absolute path,
    or a symlink name simply fails to match any real entry, so there is no
    hostile value to contain and no containment check to get wrong.

    Symlinks are not followed. ``entry.is_dir(follow_symlinks=False)`` defaults to following them,
    which would return ``root/escape`` for a link pointing out of the tree and
    hand the caller an escape hatch. Listing-based resolution is only safe
    when the entry is a real directory, so this asks for that explicitly.
    A matching entry that IS a symlinked directory logs a warning before the
    None: an owner who relocated a data dir and symlinked it back would
    otherwise see their project silently render as empty, with nothing
    anywhere saying why (the policy plus the fix for that silence is this
    function; the decision record is PR #1062).

    Prefer this over ``contained_path(root / name, root)`` whenever *name*
    comes from a request and names something that must already exist. Reach
    for :func:`contained_path` only when the target may legitimately not exist
    yet (new project registration, a clone destination), where matching
    against a listing is impossible.

    A None result means *absent*, not *invalid*: callers run
    :func:`validate_path_segment` first, so a syntactically bad name is
    already rejected upstream. Map None to "not found", not "bad request".
    """
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if entry.name != name:
                    continue
                # Names are unique within a directory — nothing else can match.
                return _match_child_entry(entry, root, name)
    except OSError:
        return None
    return None


def contained_path(candidate: str | Path, root: str | Path) -> str:
    """Return *candidate* resolved, guaranteed to sit inside *root*.

    Raises ValueError when it escapes. Symlinks are followed, so a link
    pointing out of the root is rejected on its real target.

    Two things about the implementation are deliberate and should survive
    future cleanups:

    1. It uses ``os.path.realpath`` + ``startswith(root + os.sep)`` rather than
       the more idiomatic ``Path.resolve().is_relative_to()``. Both are correct,
       but static analysers (CodeQL's ``py/path-injection`` among them) only
       model the former as a containment barrier. Written the idiomatic way,
       every guarded flow from a request parameter down to a file read still
       reports as an unguarded path injection.
    2. It *returns* the safe path instead of raising-only. Callers must use the
       return value and discard their own variable. A validator that only
       raises leaves the original tainted value flowing to the sink, so no
       amount of checking inside it registers as a barrier.
    """
    real = os.path.realpath(str(candidate))
    root_real = os.path.realpath(str(root))
    if real != root_real and not real.startswith(root_real + os.sep):
        raise ValueError(
            f"Path escapes its root directory: {candidate!r} is not inside {root!r}. "
            "Ensure the path has no '..' segments or symlinks leaving the root."
        )
    return real
