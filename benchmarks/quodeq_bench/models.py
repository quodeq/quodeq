"""Ground-truth data model for benchmark cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DIMENSIONS: tuple[str, ...] = (
    "security",
    "reliability",
    "maintainability",
    "performance",
    "flexibility",
    "usability",
)
SEVERITIES: tuple[str, ...] = ("critical", "major", "minor")


class TruthError(ValueError):
    """Raised when a truth.json file is structurally invalid."""


@dataclass(frozen=True)
class Label:
    file: str
    line: int
    dimension: str
    severity: str
    note: str
    anchor: str | None = None
    end_line: int | None = None
    cwes: tuple[int, ...] = ()
    reqs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseTruth:
    case_id: str
    language: str
    exhaustive: bool
    clean_files: tuple[str, ...]
    labels: tuple[Label, ...]


def _parse_label(raw: dict, index: int) -> Label:
    if not isinstance(raw, dict):
        raise TruthError(f"label {index}: must be an object")
    file_value = raw.get("file")
    if not isinstance(file_value, str) or not file_value:
        raise TruthError(f"label {index}: file must be a non-empty string, got {file_value!r}")
    line = raw.get("line")
    if not isinstance(line, int) or line < 1:
        raise TruthError(f"label {index}: line must be a positive int, got {line!r}")
    dimension = raw.get("dimension")
    if dimension not in DIMENSIONS:
        raise TruthError(f"label {index}: unknown dimension {dimension!r}")
    severity = raw.get("severity")
    if severity not in SEVERITIES:
        raise TruthError(f"label {index}: unknown severity {severity!r}")
    cwes = tuple(int(c) for c in raw.get("cwes", []))
    reqs = tuple(str(r) for r in raw.get("reqs", []))
    if not cwes and not reqs:
        raise TruthError(f"label {index}: cwes and reqs are both empty")
    end_line = raw.get("end_line")
    if end_line is not None and (not isinstance(end_line, int) or end_line < line):
        raise TruthError(f"label {index}: end_line must be >= line")
    return Label(
        file=file_value,
        line=line,
        dimension=dimension,
        severity=severity,
        note=str(raw.get("note", "")),
        anchor=raw.get("anchor"),
        end_line=end_line,
        cwes=cwes,
        reqs=reqs,
    )


def load_truth(case_dir: Path) -> CaseTruth:
    truth_path = case_dir / "truth.json"
    try:
        raw = json.loads(truth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TruthError(f"{truth_path}: {exc}") from exc
    raw_labels = raw.get("labels", [])
    if not isinstance(raw_labels, list):
        raise TruthError(f"{truth_path}: labels must be a list, got {type(raw_labels).__name__}")
    labels = tuple(
        _parse_label(item, i) for i, item in enumerate(raw_labels)
    )
    if not labels:
        raise TruthError(f"{truth_path}: no labels")
    return CaseTruth(
        case_id=case_dir.name,
        language=str(raw.get("language", "python")),
        exhaustive=bool(raw.get("exhaustive", False)),
        clean_files=tuple(str(f) for f in raw.get("clean_files", [])),
        labels=labels,
    )
