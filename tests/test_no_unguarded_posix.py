"""Ratchet: no NEW POSIX-only process/signal calls or unix-only shell commands.

These break on Windows: ``os.killpg``/``getpgid``/``fork``/``setsid``/``setpgrp``
do not exist there, and shelling out to ``pgrep``/``ps``/``pkill``/``lsof``
raises ``FileNotFoundError``. Existing call sites are already either win32-guarded
or wrapped to degrade gracefully (audited 2026-05-30) and are listed in
``_ALLOWLIST``. Any NEW occurrence fails this test until it is guarded behind
``sys.platform``/``IS_WIN32`` (or given a cross-platform alternative) and added
here with a justification.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "quodeq"

_PATTERNS = re.compile(
    r"\bos\.(killpg|getpgid|fork|setsid|setpgrp)\(|"
    r"""\[\s*['"](pgrep|pkill|lsof|ps)['"]"""
)

# Known, already-handled sites (src-relative "path.py:LINE"). Audited 2026-05-30.
_ALLOWLIST: set[str] = {
    # kill_tree POSIX branch, in the else of `if sys.platform == "win32"`
    # (win32 uses taskkill /F /T). Hoisted from analysis/_process.py so
    # services/ and analysis/ can share one implementation.
    "shared/_process_kill.py:29",
    # kill_proc_tree POSIX branch, in the else of `if sys.platform == "win32"`
    # (win32 uses taskkill /F /T). Hoisted from assistant to shared.
    "shared/_process_kill.py:71",
    # pgrep / ps are wrapped in `except (OSError, ...)` -> returns _UNKNOWN, so
    # on Windows (FileNotFoundError) resource sampling degrades gracefully.
    "shared/resource_sampler.py:41",
    "shared/resource_sampler.py:57",
    # child_cwd's macOS branch: only reached when `platform == "darwin"` and
    # wrapped in `except (..., subprocess.SubprocessError)`, so Windows never
    # runs it and a missing lsof degrades to None. Used to resolve clickable
    # terminal links against the shell's live cwd.
    "terminal/links.py:80",
    # quodeq/menubar/ is darwin-only by construction: control.is_supported()
    # gates every spawn on sys.platform == "darwin", and app/_app_lifecycle
    # only run inside the rumps process that spawn starts. lsof/killpg/pkill
    # are therefore never reached on Windows, and each call is wrapped to
    # degrade gracefully anyway.
    "menubar/_process.py:75",
    "menubar/_app_lifecycle.py:150",
    "menubar/_app_lifecycle.py:158",
}


def _offenders() -> list[str]:
    bad: list[str] = []
    for py in sorted(SRC.rglob("*.py")):
        rel = py.relative_to(SRC).as_posix()
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if _PATTERNS.search(line) and f"{rel}:{i}" not in _ALLOWLIST:
                bad.append(f"{rel}:{i}: {line.strip()}")
    return bad


def test_no_new_unguarded_posix() -> None:
    offenders = _offenders()
    assert not offenders, (
        f"{len(offenders)} new POSIX-only call(s) that break on Windows. Guard "
        "behind sys.platform/IS_WIN32 (and add to _ALLOWLIST with a reason) or "
        "use a cross-platform alternative:\n  " + "\n  ".join(offenders)
    )
