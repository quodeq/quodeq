"""Running jscpd and turning its JSON report into ratchet keys.

Split out of tools/check_clones.py so the checker stays small: this module
owns the subprocess call (jscpd lives in the UI package's devDependencies)
and the report -> `Clone` translation; check_clones.py owns the baseline.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPORT_NAME = "jscpd-report.json"

INSTALL_HINT = (
    "jscpd is not available. Install the UI dev dependencies first:\n"
    "    cd src/quodeq/ui && npm install"
)


class JscpdUnavailable(RuntimeError):
    """jscpd could not be run (not installed, or it produced no report)."""


@dataclass(frozen=True, slots=True)
class Clone:
    """One duplicated fragment pair, keyed by its two repo-relative spans."""

    key: str
    fmt: str
    lines: int


def ui_dir(repo_root: Path) -> Path:
    """The UI package directory, which owns the jscpd devDependency."""
    return repo_root / "src" / "quodeq" / "ui"


def jscpd_command(repo_root: Path, output_dir: Path) -> list[str]:
    """The jscpd invocation: root config, JSON report into *output_dir*."""
    return [
        "npx", "--no-install", "jscpd",
        "--config", str(repo_root / ".jscpd.json"),
        "--reporters", "json",
        "--output", str(output_dir),
        "--silent",
    ]


def _relative(name: str, base_dir: Path, repo_root: Path) -> str:
    """Map a jscpd file name (relative to *base_dir*) to a repo-relative one."""
    absolute = os.path.normpath(os.path.join(str(base_dir), name))
    return Path(os.path.relpath(absolute, str(repo_root))).as_posix()


def _span(entry: dict[str, Any], base_dir: Path, repo_root: Path) -> str:
    rel = _relative(str(entry["name"]), base_dir, repo_root)
    return f"{rel}:{entry['start']}-{entry['end']}"


def parse_report(payload: dict[str, Any], base_dir: Path, repo_root: Path) -> list[Clone]:
    """Return the report's duplicates as sorted, de-duplicated `Clone`s.

    jscpd reports file names relative to the directory it ran in
    (*base_dir*); keys are repo-relative and the pair is sorted so the same
    duplication keys identically whichever copy jscpd lists first.
    """
    seen: dict[str, Clone] = {}
    for entry in payload.get("duplicates") or []:
        first = _span(entry["firstFile"], base_dir, repo_root)
        second = _span(entry["secondFile"], base_dir, repo_root)
        key = "|".join(sorted((first, second)))
        seen.setdefault(key, Clone(
            key=key,
            fmt=str(entry.get("format", "")),
            lines=int(entry.get("lines", 0)),
        ))
    return [seen[key] for key in sorted(seen)]


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command), cwd=str(cwd), capture_output=True, text=True, check=False,
        )
    except OSError as e:  # npx itself missing
        raise JscpdUnavailable(f"{INSTALL_HINT}\n  ({e})") from e


def run_jscpd(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    """Run jscpd from the UI package and return its parsed JSON report."""
    cwd = ui_dir(repo_root)
    proc = _run(jscpd_command(repo_root, output_dir), cwd)
    report = Path(output_dir) / REPORT_NAME
    if not report.exists():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise JscpdUnavailable(f"{INSTALL_HINT}\n  (jscpd wrote no report: {detail})")
    try:
        return json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise JscpdUnavailable(f"unreadable jscpd report at {report}: {e}") from e
