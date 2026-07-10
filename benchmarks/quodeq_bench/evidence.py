"""Parse quodeq evidence JSONL output into Finding records."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    dimension: str
    file: str
    line: int
    severity: str
    req: str
    vt: str
    refs: tuple[str, ...]
    title: str


def parse_cwe_refs(refs: Iterable[str]) -> tuple[int, ...]:
    out: list[int] = []
    for ref in refs:
        text = str(ref).strip().upper()
        if text.startswith("CWE-"):
            suffix = text[4:]
            if suffix.isdigit():
                out.append(int(suffix))
    return tuple(out)


def _finding_from_line(obj: dict) -> Finding | None:
    if obj.get("t") != "violation":
        return None
    line = obj.get("line")
    if not isinstance(line, int) or line < 1:
        return None
    return Finding(
        dimension=str(obj.get("d", "")),
        file=str(obj.get("file", "")),
        line=line,
        severity=str(obj.get("severity", "")),
        req=str(obj.get("req", "")),
        vt=str(obj.get("vt", "")),
        refs=tuple(str(r) for r in obj.get("refs", [])),
        title=str(obj.get("w", "")),
    )


def load_findings(evidence_dir: Path) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    errored: list[str] = []
    for jsonl in sorted(evidence_dir.glob("*_evidence.jsonl")):
        for raw_line in jsonl.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("_marker") == "file_done":
                if obj.get("status") == "error":
                    errored.append(str(obj.get("file", "")))
                continue
            finding = _finding_from_line(obj)
            if finding is not None:
                findings.append(finding)
    return findings, errored


def find_evidence_dir(output_root: Path) -> Path | None:
    if not output_root.is_dir():
        return None
    candidates = [
        d
        for d in output_root.rglob("evidence")
        if d.is_dir() and any(d.glob("*_evidence.jsonl"))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)
