"""Fail-soft manifest reading helpers for project-shape detection.

Split from ``project_shape.py`` to keep that file under the size ratchet's
300-line cap. Moved verbatim. Every reader here returns ``None`` (logging at
debug for absence, warning for an unreadable-but-present manifest) rather
than raising -- see the module docstring on ``project_shape.py`` for why
nothing here may raise.
"""
from __future__ import annotations

import json
import logging
import re
import tomllib
from pathlib import Path

# Named after the facade module, not __name__: tests scope caplog to logger
# "quodeq.context.project_shape" (the pre-split module name), and this
# logging call moved here verbatim from that module.
_logger = logging.getLogger("quodeq.context.project_shape")

#: Detection probes every manifest it knows about, so most repos miss most of
#: them: a Python project has no Cargo.toml, and Quodeq's own root has neither
#: Cargo.toml nor package.json. Absence is the expected case and belongs at
#: debug. A manifest that exists and still cannot be read -- no permission, a
#: truncated file, a parser blowing its stack -- is a signal we meant to have
#: and lost, so that stays at WARNING.
#:
#: The exception type cannot carry that split on its own: opening a directory
#: raises IsADirectoryError on POSIX but PermissionError (WinError 5) on
#: Windows, which is indistinguishable from a genuine permission denial. So
#: the not-a-file cases are settled up front by ``_manifest_missing`` (the
#: same ``is_file()`` gate ``trust_model._read_profile`` uses) and the catch
#: below only has to cover a file that disappears between the check and the
#: open -- a race nobody can act on, so it stays quiet too.
_ABSENT_MANIFEST = (FileNotFoundError, IsADirectoryError, NotADirectoryError)


def _manifest_missing(path: Path) -> bool:
    """True when *path* is not a readable regular file, on any platform.

    ``Path.is_file()`` swallows its own OSError and answers False for a
    missing entry, a directory and a broken symlink alike, which is exactly
    the set that means "this project does not ship this manifest".
    """
    if path.is_file():
        return False
    _logger.debug("No manifest at %s", path)
    return True


def _read_text(path: Path) -> str | None:
    if _manifest_missing(path):
        return None
    try:
        return path.read_text(encoding="utf-8")
    except _ABSENT_MANIFEST:
        _logger.debug("Manifest %s vanished mid-scan", path)
        return None
    except Exception as exc:  # noqa: BLE001 - detection must never fail a scan
        _logger.warning("Ignoring unreadable manifest %s: %s", path, exc)
        return None


def _read_toml(path: Path) -> dict[str, object] | None:
    if _manifest_missing(path):
        return None
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except _ABSENT_MANIFEST:
        _logger.debug("Manifest %s vanished mid-scan", path)
        return None
    except Exception as exc:  # noqa: BLE001 - detection must never fail a scan
        # Wider than OSError/TOMLDecodeError on purpose: tomllib is a
        # recursive-descent parser, so deeply nested tables overflow the stack
        # and raise RecursionError. It bottoms out far shallower than the C
        # JSON decoder -- a few thousand levels, not tens of thousands.
        _logger.warning("Ignoring unreadable TOML manifest %s: %s", path, exc)
        return None


def _read_json(path: Path) -> dict[str, object] | None:
    # Absence is already handled quietly by _read_text, so reaching the handler
    # below means the file exists and its contents are unusable.
    text = _read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001 - detection must never fail a scan
        # Wider than json.JSONDecodeError: deeply nested arrays exhaust the C
        # decoder's call stack and raise RecursionError, a RuntimeError.
        _logger.warning("Ignoring unreadable JSON manifest %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def _flat_dep_names(*sources: object) -> list[str]:
    out: list[str] = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in src:
            out.append(str(key).lower())
    return out


def _matches_any(haystack: list[str], needles: tuple[str, ...]) -> list[str]:
    needle_set = {n.lower() for n in needles}
    return [n for n in haystack if n in needle_set]


_DEP_SPEC_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


def _strip_dep_spec(spec: str) -> str:
    """Reduce a PEP 508 spec like ``flask>=3.0`` to its bare name."""
    m = _DEP_SPEC_RE.match(spec.strip())
    return m.group(1) if m else spec.strip()
