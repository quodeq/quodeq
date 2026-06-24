"""Shared helpers for the provenance-gate regression tests (issue #641).

Dependency-light on purpose (only pathlib/json) so BOTH the always-on
structural tests (``test_prompt_provenance_gate.py``) and the opt-in live
behavioral test (``test_provenance_gate_behavioral.py``) can import it,
including in a CI environment that has no ollama and never imports the
model-calling code.

The fixtures under ``fixtures/provenance_gate/`` are a matrix of cases:

  internal_*  — code that run fa56db32 rated `critical` but whose flagged
                value is provably INTERNAL (a defaulted prop/arg, a content
                hash). Vendored byte-for-byte from commit a84ab6f8 (before the
                later code-hardening at c0edcd6f / 521f46c6) so the fixture is
                the exact code that was rated critical. Expected: not critical.
  external_*  — synthetic code whose flagged value is genuinely ATTACKER-
                CONTROLLED (an HTTP field, a CLI arg, a response header).
                Expected: stays critical — the guard that the gate does not
                over-relax.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "provenance_gate"

_SEVERITY_ORDER = {"minor": 1, "major": 2, "critical": 3}


@dataclass(frozen=True)
class GateCase:
    """One row of the provenance-gate matrix."""

    name: str
    repo_dir: Path  # the repo/ root, passed as assemble_api_prompt(repo_root=...)
    source_file: Path  # the single source file under repo/
    expected: dict


def discover_cases() -> list[GateCase]:
    """Glob the fixture matrix. Returns [] if the dir is missing (never raises)."""
    cases: list[GateCase] = []
    if not FIXTURES_ROOT.is_dir():
        return cases
    for entry in sorted(FIXTURES_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        expected_file = entry / "expected.json"
        repo_dir = entry / "repo"
        if not expected_file.is_file() or not repo_dir.is_dir():
            continue
        meta = json.loads(expected_file.read_text(encoding="utf-8"))
        source_file = repo_dir / meta["display_file"]
        cases.append(
            GateCase(
                name=entry.name,
                repo_dir=repo_dir,
                source_file=source_file,
                expected=meta,
            )
        )
    return cases


def severity_str(finding: dict) -> str | None:
    """Normalise a finding's severity to a plain string ('critical'/'major'/'minor').

    ``_call_api`` returns ``_Finding.model_dump()`` dicts whose ``severity`` is a
    ``(str, Enum)`` member; ``.value`` yields the bare string. Falls back to the
    value as-is if it is already a string.
    """
    sev = finding.get("severity")
    if sev is None:
        return None
    return getattr(sev, "value", sev)


def target_severity(
    findings: list[dict], expected: dict, *, allow_req_only: bool = False
) -> tuple[str | None, list[dict]]:
    """Worst severity among findings that match the case's target construct.

    A finding matches when (robust to line drift / the model quoting a
    neighbouring line):
      - the case ``construct`` token appears in its snippet / title / reason, OR
      - its line span covers the case ``target_line``.

    ``allow_req_only`` additionally matches any finding whose requirement id
    equals the case ``req``. That is a deliberately LOOSE catch for the external
    controls, whose single-purpose fixtures contain exactly one issue, so any
    same-req critical is the one we want. It is OFF for internal cases: those
    fixtures (e.g. GradeBoundaryBar) contain other genuine same-req sites, and a
    bare req match would let an unrelated critical there spuriously fail the
    'gate kept the target non-critical' assertion.

    Returns ``(worst_severity | None, matching_findings)``. ``None`` means the
    construct was not flagged at all this run.
    """
    req = expected.get("req")
    construct = expected.get("construct") or ""
    target_line = expected.get("target_line") or 0
    matches: list[dict] = []
    for f in findings:
        blob = " ".join(str(f.get(k) or "") for k in ("snippet", "w", "reason"))
        line = f.get("line") or 0
        end = f.get("end_line") or line
        line_hit = bool(line) and line <= target_line <= end
        construct_hit = bool(construct) and construct in blob
        req_hit = allow_req_only and bool(req) and f.get("req") == req
        if construct_hit or line_hit or req_hit:
            matches.append(f)
    worst: str | None = None
    for f in matches:
        sev = severity_str(f)
        if sev in _SEVERITY_ORDER and (worst is None or _SEVERITY_ORDER[sev] > _SEVERITY_ORDER[worst]):
            worst = sev
    return worst, matches
