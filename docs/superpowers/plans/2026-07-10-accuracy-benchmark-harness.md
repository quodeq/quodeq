# Accuracy Benchmark Harness (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A black-box benchmark harness that runs `quodeq evaluate` over a labeled synthetic corpus, computes per-dimension precision/recall, and gates CI on regressions.

**Architecture:** New top-level `benchmarks/` directory (outside `src/quodeq`, not shipped in the wheel) containing a plain-Python package `quodeq_bench` (models → evidence parser → matcher → metrics → report → compare → runner → CLI) plus a hand-authored synthetic corpus with self-validating `truth.json` labels. The harness only shells out to the `quodeq` CLI and parses the evidence JSONL it already emits.

**Tech Stack:** Python 3.12+ stdlib only (no new dependencies), pytest 9, uv, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-07-10-accuracy-benchmark-harness-design.md` — read it first.

## Global Constraints

- Python `>=3.12`; repo uses `uv` (build backend `uv_build`); run everything via `uv run ...`.
- `quodeq_bench` uses **stdlib only** — no new runtime dependencies.
- Tests live in `tests/benchmarks/`, run with `uv run pytest tests/benchmarks/ -q`; per-test timeout is 60s (repo-wide config); no test may call a real model.
- Dimension ids (exact): `security`, `reliability`, `maintainability`, `performance`, `flexibility`, `usability`. Severities: `critical`, `major`, `minor`.
- Evidence JSONL line fields (exact, from `src/quodeq/analysis/mcp/router.py`): `schema_version`, `p`, `t` (`violation`|`compliance`), `d` (dimension), `w` (title), `file`, `line`, `snippet`, `severity`, `reason`, `req`, `vt`, `refs` (list like `["CWE-598", "OWASP-A02"]`), optional `confidence`. Marker lines: `{"_marker": "file_done", "file": ..., "status": "ok"|"error", ...}`.
- CLI contract: `quodeq evaluate <repo> -d <csv-dims> --clean-scan -o <outdir> --time-limit <secs> --n-subagents <n>`; provider/model via env `AI_PROVIDER` / `AI_MODEL`.
- Commit messages: conventional (`feat:`, `test:`, `ci:`, `docs:`), **no AI attribution / no Co-Authored-By lines**.
- Match rule (from spec): same normalized file + line within ±5 (or overlapping label span) + class match (finding CWE refs ∩ label `cwes`, OR finding `req` ∈ label `reqs`). Compliance findings ignored. FPs counted only in exhaustive cases or declared `clean_files`.

---

### Task 1: Branch, scaffolding, docs commit

**Files:**
- Create: `benchmarks/quodeq_bench/__init__.py`, `benchmarks/results/.gitignore`, `benchmarks/README.md`
- Modify: `pyproject.toml` (pytest `pythonpath`)
- Commit: `docs/superpowers/specs/2026-07-10-accuracy-benchmark-harness-design.md`, `docs/superpowers/plans/2026-07-10-accuracy-benchmark-harness.md`

**Interfaces:**
- Produces: importable package `quodeq_bench` for all later tasks (`from quodeq_bench.models import ...` works under pytest).

- [ ] **Step 1: Branch off fresh develop**

```bash
cd /Users/marche000/Projects/vik/quodeq
git fetch origin develop
git checkout -b feat/benchmark-harness origin/develop
```

- [ ] **Step 2: Create scaffolding**

`benchmarks/quodeq_bench/__init__.py`:
```python
"""Accuracy benchmark harness for quodeq. Dev tooling — not shipped in the wheel."""
```

`benchmarks/results/.gitignore`:
```
*
!.gitignore
!published/
!published/**
```

`benchmarks/README.md`:
```markdown
# Quodeq accuracy benchmarks

Dev/release tooling that measures quodeq's finding accuracy against a
labeled corpus. Not shipped in the wheel. See
`docs/superpowers/specs/2026-07-10-accuracy-benchmark-harness-design.md`.

## Run locally

```bash
PYTHONPATH=benchmarks uv run python -m quodeq_bench run \
  --corpus benchmarks/corpus/synthetic \
  --provider claude --model claude-haiku-4-5-20251001 \
  --out benchmarks/results/local
PYTHONPATH=benchmarks uv run python -m quodeq_bench markdown benchmarks/results/local/report.json
```

## Compare / gate

```bash
PYTHONPATH=benchmarks uv run python -m quodeq_bench compare \
  benchmarks/baselines/gate.json benchmarks/results/local/report.json --threshold 0.05
```

Exit codes: 0 ok, 1 regression, 2 errored run.

## Tests (no model calls)

```bash
uv run pytest tests/benchmarks/ -q
```
```

- [ ] **Step 3: Make `quodeq_bench` importable under pytest**

In `pyproject.toml`, find `[tool.pytest.ini_options]` and change the `pythonpath` line:

```toml
pythonpath = ["src", "benchmarks"]
```

- [ ] **Step 4: Verify pytest still collects**

Run: `uv run pytest tests/ -q --co -m "not integration" | tail -3`
Expected: collection succeeds, no errors.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-07-10-accuracy-benchmark-harness-design.md \
        docs/superpowers/plans/2026-07-10-accuracy-benchmark-harness.md \
        benchmarks/ pyproject.toml
git commit -m "docs: add benchmark harness spec, plan, and scaffolding"
```

---

### Task 2: Truth models and loader (`models.py`)

**Files:**
- Create: `benchmarks/quodeq_bench/models.py`
- Test: `tests/benchmarks/test_models.py`

**Interfaces:**
- Produces:
  - `DIMENSIONS: tuple[str, ...]`, `SEVERITIES: tuple[str, ...]`
  - `class TruthError(ValueError)`
  - `@dataclass(frozen=True) Label(file: str, line: int, dimension: str, severity: str, note: str, anchor: str | None = None, end_line: int | None = None, cwes: tuple[int, ...] = (), reqs: tuple[str, ...] = ())`
  - `@dataclass(frozen=True) CaseTruth(case_id: str, language: str, exhaustive: bool, clean_files: tuple[str, ...], labels: tuple[Label, ...])`
  - `load_truth(case_dir: Path) -> CaseTruth` (raises `TruthError` on invalid content)

- [ ] **Step 1: Write the failing tests**

`tests/benchmarks/test_models.py`:
```python
import json
from pathlib import Path

import pytest

from quodeq_bench.models import CaseTruth, TruthError, load_truth

_VALID = {
    "language": "python",
    "exhaustive": True,
    "clean_files": ["storage.py"],
    "labels": [
        {
            "file": "app.py",
            "line": 13,
            "anchor": 'f"SELECT',
            "dimension": "security",
            "cwes": [89, 564],
            "reqs": [],
            "severity": "critical",
            "note": "f-string SQL",
        }
    ],
}


def _write_case(tmp_path: Path, payload: dict) -> Path:
    case = tmp_path / "py-sec-basic"
    case.mkdir()
    (case / "truth.json").write_text(json.dumps(payload), encoding="utf-8")
    return case


def test_load_valid_truth(tmp_path: Path) -> None:
    truth = load_truth(_write_case(tmp_path, _VALID))
    assert isinstance(truth, CaseTruth)
    assert truth.case_id == "py-sec-basic"
    assert truth.exhaustive is True
    assert truth.labels[0].cwes == (89, 564)
    assert truth.labels[0].dimension == "security"


def test_rejects_unknown_dimension(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["labels"][0]["dimension"] = "velocity"
    with pytest.raises(TruthError, match="dimension"):
        load_truth(_write_case(tmp_path, bad))


def test_rejects_label_without_class(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["labels"][0]["cwes"] = []
    bad["labels"][0]["reqs"] = []
    with pytest.raises(TruthError, match="cwes"):
        load_truth(_write_case(tmp_path, bad))


def test_rejects_nonpositive_line(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["labels"][0]["line"] = 0
    with pytest.raises(TruthError, match="line"):
        load_truth(_write_case(tmp_path, bad))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/benchmarks/test_models.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'quodeq_bench.models'`

- [ ] **Step 3: Implement `models.py`**

`benchmarks/quodeq_bench/models.py`:
```python
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
        file=str(raw["file"]),
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
    labels = tuple(
        _parse_label(item, i) for i, item in enumerate(raw.get("labels", []))
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/benchmarks/test_models.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add benchmarks/quodeq_bench/models.py tests/benchmarks/test_models.py
git commit -m "feat(bench): truth.json data model and loader"
```

---

### Task 3: Evidence parser (`evidence.py`)

**Files:**
- Create: `benchmarks/quodeq_bench/evidence.py`
- Test: `tests/benchmarks/test_evidence.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `@dataclass(frozen=True) Finding(dimension: str, file: str, line: int, severity: str, req: str, vt: str, refs: tuple[str, ...], title: str)`
  - `parse_cwe_refs(refs: Iterable[str]) -> tuple[int, ...]` — `["CWE-89", "OWASP-A03"]` → `(89,)`
  - `load_findings(evidence_dir: Path) -> tuple[list[Finding], list[str]]` — (violations, errored_files); skips `_marker` lines and `t == "compliance"`.
  - `find_evidence_dir(output_root: Path) -> Path | None` — newest dir named `evidence` containing `*_evidence.jsonl`, searched recursively.

- [ ] **Step 1: Write the failing tests**

`tests/benchmarks/test_evidence.py`:
```python
import json
from pathlib import Path

from quodeq_bench.evidence import (
    Finding,
    find_evidence_dir,
    load_findings,
    parse_cwe_refs,
)

_VIOLATION = {
    "schema_version": 1,
    "p": "Confidentiality",
    "t": "violation",
    "d": "security",
    "w": "SQL injection via f-string",
    "file": "app.py",
    "line": 13,
    "snippet": 'query = f"SELECT * FROM users WHERE id = {user_id}"',
    "severity": "critical",
    "reason": "User input concatenated into SQL.",
    "req": "S-CON-1",
    "vt": "sql-injection",
    "refs": ["CWE-89", "OWASP-A03"],
}
_COMPLIANCE = dict(_VIOLATION, t="compliance", w="parameterized query", line=5)
_MARKER_OK = {"_marker": "file_done", "file": "app.py", "status": "ok"}
_MARKER_ERR = {"_marker": "file_done", "file": "broken.py", "status": "error"}


def _write_evidence(tmp_path: Path) -> Path:
    evidence = tmp_path / "run" / "evidence"
    evidence.mkdir(parents=True)
    lines = [_VIOLATION, _COMPLIANCE, _MARKER_OK, _MARKER_ERR]
    (evidence / "security_evidence.jsonl").write_text(
        "\n".join(json.dumps(obj) for obj in lines) + "\n", encoding="utf-8"
    )
    return evidence


def test_parse_cwe_refs() -> None:
    assert parse_cwe_refs(["CWE-89", "OWASP-A03", "cwe-798"]) == (89, 798)


def test_load_findings_skips_markers_and_compliance(tmp_path: Path) -> None:
    findings, errored = load_findings(_write_evidence(tmp_path))
    assert len(findings) == 1
    assert findings[0] == Finding(
        dimension="security",
        file="app.py",
        line=13,
        severity="critical",
        req="S-CON-1",
        vt="sql-injection",
        refs=("CWE-89", "OWASP-A03"),
        title="SQL injection via f-string",
    )
    assert errored == ["broken.py"]


def test_load_findings_tolerates_malformed_lines(tmp_path: Path) -> None:
    evidence = _write_evidence(tmp_path)
    path = evidence / "security_evidence.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    findings, _ = load_findings(evidence)
    assert len(findings) == 1


def test_find_evidence_dir(tmp_path: Path) -> None:
    evidence = _write_evidence(tmp_path)
    assert find_evidence_dir(tmp_path) == evidence
    assert find_evidence_dir(tmp_path / "nowhere") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/benchmarks/test_evidence.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'quodeq_bench.evidence'`

- [ ] **Step 3: Implement `evidence.py`**

`benchmarks/quodeq_bench/evidence.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/benchmarks/test_evidence.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add benchmarks/quodeq_bench/evidence.py tests/benchmarks/test_evidence.py
git commit -m "feat(bench): evidence JSONL parser"
```

---

### Task 4: Matcher (`matcher.py`)

**Files:**
- Create: `benchmarks/quodeq_bench/matcher.py`
- Test: `tests/benchmarks/test_matcher.py`

**Interfaces:**
- Consumes: `Label`, `CaseTruth` from `quodeq_bench.models`; `Finding`, `parse_cwe_refs` from `quodeq_bench.evidence`.
- Produces:
  - `LINE_WINDOW = 5`
  - `normalize_path(path: str) -> str`
  - `@dataclass(frozen=True) CaseMatch(total_labels: int, matched_labels: int, matched_findings: int, fp_findings: int, duplicates: int, severity_agreements: int)`
  - `match_case(truth: CaseTruth, findings: Sequence[Finding]) -> dict[str, CaseMatch]` — keyed by dimension; every dimension with ≥1 label or ≥1 counted FP appears.

- [ ] **Step 1: Write the failing tests**

`tests/benchmarks/test_matcher.py`:
```python
from quodeq_bench.evidence import Finding
from quodeq_bench.matcher import CaseMatch, match_case, normalize_path
from quodeq_bench.models import CaseTruth, Label


def _finding(**overrides) -> Finding:
    base = dict(
        dimension="security",
        file="app.py",
        line=13,
        severity="critical",
        req="S-CON-1",
        vt="sql-injection",
        refs=("CWE-89",),
        title="SQLi",
    )
    base.update(overrides)
    return Finding(**base)


def _truth(labels: tuple[Label, ...], exhaustive: bool = True) -> CaseTruth:
    return CaseTruth(
        case_id="case",
        language="python",
        exhaustive=exhaustive,
        clean_files=(),
        labels=labels,
    )


_SQLI = Label(
    file="app.py", line=13, dimension="security", severity="critical",
    note="sqli", cwes=(89, 564), reqs=(),
)


def test_normalize_path() -> None:
    assert normalize_path("./src\\app.py") == "src/app.py"


def test_exact_match_by_cwe() -> None:
    result = match_case(_truth((_SQLI,)), [_finding()])
    assert result["security"] == CaseMatch(
        total_labels=1, matched_labels=1, matched_findings=1,
        fp_findings=0, duplicates=0, severity_agreements=1,
    )


def test_match_within_line_window_and_req() -> None:
    label = Label(
        file="orders.py", line=40, dimension="maintainability",
        severity="major", note="god fn", cwes=(), reqs=("M-MOD-1",),
    )
    finding = _finding(
        dimension="maintainability", file="orders.py", line=44,
        severity="minor", req="M-MOD-1", refs=(),
    )
    result = match_case(_truth((label,)), [finding])
    assert result["maintainability"].matched_labels == 1
    assert result["maintainability"].severity_agreements == 0


def test_no_match_outside_window() -> None:
    result = match_case(_truth((_SQLI,)), [_finding(line=25)])
    assert result["security"].matched_labels == 0
    assert result["security"].fp_findings == 1


def test_wrong_class_is_fp_when_exhaustive() -> None:
    result = match_case(_truth((_SQLI,)), [_finding(refs=("CWE-798",), req="X-1")])
    assert result["security"].matched_labels == 0
    assert result["security"].fp_findings == 1


def test_unmatched_ignored_when_not_exhaustive() -> None:
    result = match_case(_truth((_SQLI,), exhaustive=False), [_finding(line=99)])
    assert result["security"].fp_findings == 0


def test_duplicate_findings_count_once() -> None:
    result = match_case(_truth((_SQLI,)), [_finding(), _finding(line=14)])
    assert result["security"].matched_labels == 1
    assert result["security"].matched_findings == 2
    assert result["security"].duplicates == 1


def test_span_label_overlap() -> None:
    label = Label(
        file="cfg.py", line=1, end_line=3, dimension="security",
        severity="major", note="secrets", cwes=(798,), reqs=(),
    )
    finding = _finding(file="cfg.py", line=2, refs=("CWE-798",), severity="major")
    result = match_case(_truth((label,)), [finding])
    assert result["security"].matched_labels == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/benchmarks/test_matcher.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'quodeq_bench.matcher'`

- [ ] **Step 3: Implement `matcher.py`**

`benchmarks/quodeq_bench/matcher.py`:
```python
"""Match quodeq findings against ground-truth labels."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quodeq_bench.evidence import Finding, parse_cwe_refs
from quodeq_bench.models import CaseTruth, Label

LINE_WINDOW = 5


def normalize_path(path: str) -> str:
    text = path.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


@dataclass(frozen=True)
class CaseMatch:
    total_labels: int
    matched_labels: int
    matched_findings: int
    fp_findings: int
    duplicates: int
    severity_agreements: int


def _line_matches(label: Label, finding: Finding) -> bool:
    lo = label.line - LINE_WINDOW
    hi = (label.end_line or label.line) + LINE_WINDOW
    return lo <= finding.line <= hi


def _class_matches(label: Label, finding: Finding) -> bool:
    if label.cwes and set(label.cwes) & set(parse_cwe_refs(finding.refs)):
        return True
    if label.reqs and finding.req in label.reqs:
        return True
    return False


def _matches(label: Label, finding: Finding) -> bool:
    return (
        label.dimension == finding.dimension
        and normalize_path(label.file) == normalize_path(finding.file)
        and _line_matches(label, finding)
        and _class_matches(label, finding)
    )


def match_case(truth: CaseTruth, findings: Sequence[Finding]) -> dict[str, CaseMatch]:
    clean = {normalize_path(f) for f in truth.clean_files}
    hits: dict[int, list[Finding]] = {}
    fp_by_dim: dict[str, int] = {}

    for finding in findings:
        target: int | None = None
        for idx, label in enumerate(truth.labels):
            if _matches(label, finding):
                target = idx
                break
        if target is not None:
            hits.setdefault(target, []).append(finding)
        elif truth.exhaustive or normalize_path(finding.file) in clean:
            fp_by_dim[finding.dimension] = fp_by_dim.get(finding.dimension, 0) + 1

    dims = {label.dimension for label in truth.labels} | set(fp_by_dim)
    result: dict[str, CaseMatch] = {}
    for dim in dims:
        labels = [
            (i, label) for i, label in enumerate(truth.labels) if label.dimension == dim
        ]
        matched = [(i, label) for i, label in labels if i in hits]
        matched_findings = sum(len(hits[i]) for i, _ in matched)
        agreements = sum(
            1 for i, label in matched if hits[i][0].severity == label.severity
        )
        result[dim] = CaseMatch(
            total_labels=len(labels),
            matched_labels=len(matched),
            matched_findings=matched_findings,
            fp_findings=fp_by_dim.get(dim, 0),
            duplicates=matched_findings - len(matched),
            severity_agreements=agreements,
        )
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/benchmarks/test_matcher.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add benchmarks/quodeq_bench/matcher.py tests/benchmarks/test_matcher.py
git commit -m "feat(bench): label-to-finding matcher"
```

---

### Task 5: Metrics (`metrics.py`)

**Files:**
- Create: `benchmarks/quodeq_bench/metrics.py`
- Test: `tests/benchmarks/test_metrics.py`

**Interfaces:**
- Consumes: `CaseMatch` from `quodeq_bench.matcher`.
- Produces:
  - `@dataclass DimensionMetrics(total_labels: int = 0, matched_labels: int = 0, matched_findings: int = 0, fp: int = 0, duplicates: int = 0, severity_agreements: int = 0, kloc: float = 0.0)` with properties `precision`, `recall`, `f1`, `severity_agreement`, `duplicate_rate`, `fp_density` (all `float`, `0.0` on zero denominators) and method `as_dict() -> dict[str, float | int]`.
  - `aggregate(case_matches: Iterable[dict[str, CaseMatch]], kloc_per_case: Iterable[float]) -> dict[str, DimensionMetrics]`
  - `count_kloc(case_dir: Path, language: str) -> float` — non-empty lines of `*.py` (python) / `*.js` (javascript) files, divided by 1000; `truth.json` excluded.

- [ ] **Step 1: Write the failing tests**

`tests/benchmarks/test_metrics.py`:
```python
from pathlib import Path

from quodeq_bench.matcher import CaseMatch
from quodeq_bench.metrics import DimensionMetrics, aggregate, count_kloc


def test_aggregate_two_cases() -> None:
    case_a = {
        "security": CaseMatch(
            total_labels=2, matched_labels=1, matched_findings=2,
            fp_findings=1, duplicates=1, severity_agreements=1,
        )
    }
    case_b = {
        "security": CaseMatch(
            total_labels=2, matched_labels=2, matched_findings=2,
            fp_findings=0, duplicates=0, severity_agreements=2,
        )
    }
    metrics = aggregate([case_a, case_b], [1.0, 1.0])
    sec = metrics["security"]
    assert sec.total_labels == 4
    assert sec.matched_labels == 3
    assert sec.recall == 0.75
    assert sec.precision == 4 / 5
    assert sec.kloc == 2.0
    assert sec.fp_density == 0.5


def test_zero_denominators_are_zero() -> None:
    empty = DimensionMetrics()
    assert empty.precision == 0.0
    assert empty.recall == 0.0
    assert empty.f1 == 0.0


def test_as_dict_round_numbers() -> None:
    m = DimensionMetrics(total_labels=3, matched_labels=1)
    d = m.as_dict()
    assert d["recall"] == round(1 / 3, 4)
    assert d["total_labels"] == 3


def test_count_kloc(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n\ny = 2\n", encoding="utf-8")
    (tmp_path / "truth.json").write_text("{}", encoding="utf-8")
    assert count_kloc(tmp_path, "python") == 0.002
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/benchmarks/test_metrics.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `metrics.py`**

`benchmarks/quodeq_bench/metrics.py`:
```python
"""Aggregate match results into per-dimension accuracy metrics."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from quodeq_bench.matcher import CaseMatch

_EXTENSIONS = {"python": ".py", "javascript": ".js"}


@dataclass
class DimensionMetrics:
    total_labels: int = 0
    matched_labels: int = 0
    matched_findings: int = 0
    fp: int = 0
    duplicates: int = 0
    severity_agreements: int = 0
    kloc: float = 0.0

    @property
    def recall(self) -> float:
        return self.matched_labels / self.total_labels if self.total_labels else 0.0

    @property
    def precision(self) -> float:
        denom = self.matched_findings + self.fp
        return self.matched_findings / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def severity_agreement(self) -> float:
        return (
            self.severity_agreements / self.matched_labels
            if self.matched_labels
            else 0.0
        )

    @property
    def duplicate_rate(self) -> float:
        return self.duplicates / self.matched_labels if self.matched_labels else 0.0

    @property
    def fp_density(self) -> float:
        return self.fp / self.kloc if self.kloc else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "total_labels": self.total_labels,
            "matched_labels": self.matched_labels,
            "matched_findings": self.matched_findings,
            "fp": self.fp,
            "duplicates": self.duplicates,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "severity_agreement": round(self.severity_agreement, 4),
            "duplicate_rate": round(self.duplicate_rate, 4),
            "fp_density": round(self.fp_density, 4),
            "kloc": round(self.kloc, 3),
        }


def aggregate(
    case_matches: Iterable[dict[str, CaseMatch]],
    kloc_per_case: Iterable[float],
) -> dict[str, DimensionMetrics]:
    totals: dict[str, DimensionMetrics] = {}
    total_kloc = 0.0
    for matches, kloc in zip(case_matches, kloc_per_case, strict=True):
        total_kloc += kloc
        for dim, cm in matches.items():
            m = totals.setdefault(dim, DimensionMetrics())
            m.total_labels += cm.total_labels
            m.matched_labels += cm.matched_labels
            m.matched_findings += cm.matched_findings
            m.fp += cm.fp_findings
            m.duplicates += cm.duplicates
            m.severity_agreements += cm.severity_agreements
    for m in totals.values():
        m.kloc = total_kloc
    return totals


def count_kloc(case_dir: Path, language: str) -> float:
    ext = _EXTENSIONS.get(language, ".py")
    lines = 0
    for path in sorted(case_dir.rglob(f"*{ext}")):
        lines += sum(
            1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    return lines / 1000
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/benchmarks/test_metrics.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add benchmarks/quodeq_bench/metrics.py tests/benchmarks/test_metrics.py
git commit -m "feat(bench): per-dimension metrics aggregation"
```

---

### Task 6: Report build/write + markdown (`report.py`)

**Files:**
- Create: `benchmarks/quodeq_bench/report.py`
- Test: `tests/benchmarks/test_report.py`

**Interfaces:**
- Consumes: `DimensionMetrics` from `quodeq_bench.metrics`.
- Produces:
  - `collect_meta(repo_root: Path, provider: str, model: str, reps: int) -> dict` — keys `provider`, `model`, `reps`, `quodeq_commit` (git rev-parse HEAD, `"unknown"` on failure), `prompts_hash` (sha256 over sorted files under `src/quodeq/data/prompts`), `timestamp` (UTC ISO 8601).
  - `build_report(meta: dict, metrics: dict[str, DimensionMetrics], errored: bool = False) -> dict` — `{"meta": ..., "errored": ..., "metrics": {dim: metrics.as_dict()}}`.
  - `average_reports(reports: list[dict]) -> dict` — averages every numeric metric field per dimension across reps; meta from the first report; `errored` is OR.
  - `write_report(path: Path, report: dict) -> None` / `load_report(path: Path) -> dict`
  - `to_markdown(report: dict) -> str` — one table: dimension / precision / recall / F1 / FP density / labels.

- [ ] **Step 1: Write the failing tests**

`tests/benchmarks/test_report.py`:
```python
from pathlib import Path

from quodeq_bench.metrics import DimensionMetrics
from quodeq_bench.report import (
    average_reports,
    build_report,
    collect_meta,
    load_report,
    to_markdown,
    write_report,
)


def _report(precision: float, recall: float) -> dict:
    m = DimensionMetrics(total_labels=4, matched_labels=int(recall * 4))
    report = build_report({"model": "m", "provider": "p", "reps": 1}, {"security": m})
    report["metrics"]["security"]["precision"] = precision
    report["metrics"]["security"]["recall"] = recall
    return report


def test_build_and_roundtrip(tmp_path: Path) -> None:
    report = _report(0.8, 0.75)
    path = tmp_path / "report.json"
    write_report(path, report)
    assert load_report(path) == report
    assert report["errored"] is False


def test_average_reports() -> None:
    avg = average_reports([_report(0.8, 0.5), _report(0.6, 1.0)])
    assert avg["metrics"]["security"]["precision"] == 0.7
    assert avg["metrics"]["security"]["recall"] == 0.75
    assert avg["meta"]["model"] == "m"


def test_to_markdown_contains_dimensions() -> None:
    text = to_markdown(_report(0.8, 0.75))
    assert "| security |" in text
    assert "0.8" in text


def test_collect_meta_in_repo() -> None:
    meta = collect_meta(Path.cwd(), "claude", "haiku", 2)
    assert meta["provider"] == "claude"
    assert meta["reps"] == 2
    assert len(meta["quodeq_commit"]) >= 7
    assert len(meta["prompts_hash"]) == 64
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/benchmarks/test_report.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `report.py`**

`benchmarks/quodeq_bench/report.py`:
```python
"""Build, persist, average, and render benchmark reports."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from quodeq_bench.metrics import DimensionMetrics


def collect_meta(repo_root: Path, provider: str, model: str, reps: int) -> dict:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    digest = hashlib.sha256()
    prompts_dir = repo_root / "src" / "quodeq" / "data" / "prompts"
    for path in sorted(prompts_dir.rglob("*")):
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return {
        "provider": provider,
        "model": model,
        "reps": reps,
        "quodeq_commit": commit,
        "prompts_hash": digest.hexdigest(),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def build_report(
    meta: dict, metrics: dict[str, DimensionMetrics], errored: bool = False
) -> dict:
    return {
        "meta": meta,
        "errored": errored,
        "metrics": {dim: m.as_dict() for dim, m in sorted(metrics.items())},
    }


def average_reports(reports: list[dict]) -> dict:
    if not reports:
        raise ValueError("no reports to average")
    dims = sorted({dim for r in reports for dim in r["metrics"]})
    averaged: dict[str, dict] = {}
    for dim in dims:
        rows = [r["metrics"][dim] for r in reports if dim in r["metrics"]]
        keys = rows[0].keys()
        averaged[dim] = {
            key: round(sum(row[key] for row in rows) / len(rows), 4) for key in keys
        }
    return {
        "meta": reports[0]["meta"],
        "errored": any(r.get("errored") for r in reports),
        "metrics": averaged,
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def to_markdown(report: dict) -> str:
    meta = report["meta"]
    lines = [
        f"### Benchmark: {meta.get('provider')} / {meta.get('model')}",
        "",
        "| Dimension | Precision | Recall | F1 | FP/KLOC | Labels |",
        "|---|---|---|---|---|---|",
    ]
    for dim, m in report["metrics"].items():
        lines.append(
            f"| {dim} | {m['precision']} | {m['recall']} | {m['f1']} "
            f"| {m['fp_density']} | {m['total_labels']} |"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/benchmarks/test_report.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add benchmarks/quodeq_bench/report.py tests/benchmarks/test_report.py
git commit -m "feat(bench): report build, averaging, and markdown rendering"
```

---

### Task 7: Baseline comparison (`compare.py`)

**Files:**
- Create: `benchmarks/quodeq_bench/compare.py`
- Test: `tests/benchmarks/test_compare.py`

**Interfaces:**
- Consumes: report dicts from `quodeq_bench.report`.
- Produces:
  - `@dataclass(frozen=True) Regression(dimension: str, metric: str, baseline: float, candidate: float)`
  - `compare_reports(baseline: dict, candidate: dict, threshold: float = 0.05) -> list[Regression]` — checks `precision` and `recall` for every dimension present in `baseline["metrics"]`; a dimension missing from the candidate is a regression on both metrics (candidate value 0.0). If `baseline.get("bootstrap")` is true, returns `[]` (gate not armed yet).

- [ ] **Step 1: Write the failing tests**

`tests/benchmarks/test_compare.py`:
```python
from quodeq_bench.compare import Regression, compare_reports


def _report(precision: float, recall: float) -> dict:
    return {
        "meta": {},
        "errored": False,
        "metrics": {"security": {"precision": precision, "recall": recall}},
    }


def test_no_regression_within_threshold() -> None:
    assert compare_reports(_report(0.8, 0.8), _report(0.76, 0.79)) == []


def test_regression_beyond_threshold() -> None:
    result = compare_reports(_report(0.8, 0.8), _report(0.7, 0.8))
    assert result == [
        Regression(dimension="security", metric="precision", baseline=0.8, candidate=0.7)
    ]


def test_missing_dimension_is_regression() -> None:
    candidate = {"meta": {}, "errored": False, "metrics": {}}
    result = compare_reports(_report(0.8, 0.8), candidate)
    assert {r.metric for r in result} == {"precision", "recall"}


def test_bootstrap_baseline_never_fails() -> None:
    baseline = {"bootstrap": True, "metrics": {}}
    assert compare_reports(baseline, _report(0.0, 0.0)) == []


def test_improvement_is_not_regression() -> None:
    assert compare_reports(_report(0.5, 0.5), _report(0.9, 0.9)) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/benchmarks/test_compare.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `compare.py`**

`benchmarks/quodeq_bench/compare.py`:
```python
"""Compare a candidate benchmark report against a committed baseline."""

from __future__ import annotations

from dataclasses import dataclass

_GATED_METRICS = ("precision", "recall")


@dataclass(frozen=True)
class Regression:
    dimension: str
    metric: str
    baseline: float
    candidate: float


def compare_reports(
    baseline: dict, candidate: dict, threshold: float = 0.05
) -> list[Regression]:
    if baseline.get("bootstrap"):
        return []
    regressions: list[Regression] = []
    candidate_metrics = candidate.get("metrics", {})
    for dim, base_row in baseline.get("metrics", {}).items():
        cand_row = candidate_metrics.get(dim, {})
        for metric in _GATED_METRICS:
            base_value = float(base_row.get(metric, 0.0))
            cand_value = float(cand_row.get(metric, 0.0))
            if base_value - cand_value > threshold:
                regressions.append(
                    Regression(
                        dimension=dim, metric=metric,
                        baseline=base_value, candidate=cand_value,
                    )
                )
    return regressions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/benchmarks/test_compare.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add benchmarks/quodeq_bench/compare.py tests/benchmarks/test_compare.py
git commit -m "feat(bench): baseline comparison with regression threshold"
```

---

### Task 8: Runner (`runner.py`) — subprocess + replay

**Files:**
- Create: `benchmarks/quodeq_bench/runner.py`
- Test: `tests/benchmarks/test_runner.py`

**Interfaces:**
- Consumes: `load_findings`, `find_evidence_dir`, `Finding` from `quodeq_bench.evidence`; `CaseTruth`, `load_truth` from `quodeq_bench.models`.
- Produces:
  - `class RunError(RuntimeError)` — message describes the infrastructure failure.
  - `@dataclass(frozen=True) RunConfig(provider: str, model: str, dimensions: str = "security,reliability,maintainability,performance,flexibility,usability", time_limit: int = 900, n_subagents: int = 2, quodeq_cmd: tuple[str, ...] = ("quodeq",))`
  - `run_case(case_dir: Path, cfg: RunConfig, workdir: Path) -> list[Finding]` — copies the case (excluding `truth.json`) into `workdir/repo`, invokes `quodeq evaluate` with `--clean-scan`, env `AI_PROVIDER`/`AI_MODEL` set; raises `RunError` on non-zero exit or when no evidence dir is produced.
  - `replay_case(evidence_dir: Path) -> list[Finding]` — loads findings from a directory of `*_evidence.jsonl` (no subprocess).

- [ ] **Step 1: Write the failing tests**

The subprocess test uses a **fake quodeq** shell-out: a tiny Python script that mimics the CLI by writing an evidence file into the `-o` directory.

`tests/benchmarks/test_runner.py`:
```python
import json
import stat
import sys
from pathlib import Path

import pytest

from quodeq_bench.runner import RunConfig, RunError, replay_case, run_case

_FAKE_QUODEQ = """#!/usr/bin/env python3
import json, sys
from pathlib import Path

args = sys.argv[1:]
out = Path(args[args.index("-o") + 1])
evidence = out / "proj" / "run" / "evidence"
evidence.mkdir(parents=True)
line = {
    "schema_version": 1, "p": "Confidentiality", "t": "violation",
    "d": "security", "w": "hardcoded secret", "file": "config.py", "line": 1,
    "snippet": "API_KEY = ...", "severity": "critical", "reason": "secret",
    "req": "S-CON-1", "vt": "hardcoded-secret", "refs": ["CWE-798"],
}
(evidence / "security_evidence.jsonl").write_text(json.dumps(line) + "\\n")
"""


def _make_fake_quodeq(tmp_path: Path, body: str) -> tuple[str, ...]:
    script = tmp_path / "fake_quodeq.py"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return (sys.executable, str(script))


def _make_case(tmp_path: Path) -> Path:
    case = tmp_path / "py-sec-basic"
    case.mkdir()
    (case / "config.py").write_text('API_KEY = "sk-live-x"\n', encoding="utf-8")
    (case / "truth.json").write_text("{}", encoding="utf-8")
    return case


def test_run_case_collects_findings(tmp_path: Path) -> None:
    cfg = RunConfig(
        provider="claude", model="test-model",
        quodeq_cmd=_make_fake_quodeq(tmp_path, _FAKE_QUODEQ),
    )
    findings = run_case(_make_case(tmp_path), cfg, tmp_path / "work")
    assert len(findings) == 1
    assert findings[0].refs == ("CWE-798",)
    assert not (tmp_path / "work" / "repo" / "truth.json").exists()


def test_run_case_raises_on_nonzero_exit(tmp_path: Path) -> None:
    cfg = RunConfig(
        provider="claude", model="test-model",
        quodeq_cmd=_make_fake_quodeq(tmp_path, "import sys; sys.exit(3)\n"),
    )
    with pytest.raises(RunError, match="exit"):
        run_case(_make_case(tmp_path), cfg, tmp_path / "work")


def test_run_case_raises_when_no_evidence(tmp_path: Path) -> None:
    cfg = RunConfig(
        provider="claude", model="test-model",
        quodeq_cmd=_make_fake_quodeq(tmp_path, "pass\n"),
    )
    with pytest.raises(RunError, match="evidence"):
        run_case(_make_case(tmp_path), cfg, tmp_path / "work")


def test_replay_case(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    line = {
        "t": "violation", "d": "security", "w": "x", "file": "a.py",
        "line": 3, "severity": "major", "req": "S-CON-1", "vt": "x",
        "refs": ["CWE-89"],
    }
    (evidence / "security_evidence.jsonl").write_text(
        json.dumps(line) + "\n", encoding="utf-8"
    )
    assert len(replay_case(evidence)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/benchmarks/test_runner.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `runner.py`**

`benchmarks/quodeq_bench/runner.py`:
```python
"""Materialize a corpus case and run quodeq over it (or replay recorded evidence)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from quodeq_bench.evidence import Finding, find_evidence_dir, load_findings

_ALL_DIMENSIONS = "security,reliability,maintainability,performance,flexibility,usability"


class RunError(RuntimeError):
    """Infrastructure failure: quodeq did not produce usable evidence."""


@dataclass(frozen=True)
class RunConfig:
    provider: str
    model: str
    dimensions: str = _ALL_DIMENSIONS
    time_limit: int = 900
    n_subagents: int = 2
    quodeq_cmd: tuple[str, ...] = ("quodeq",)


def run_case(case_dir: Path, cfg: RunConfig, workdir: Path) -> list[Finding]:
    repo = workdir / "repo"
    out = workdir / "out"
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(case_dir, repo, ignore=shutil.ignore_patterns("truth.json"))
    out.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["AI_PROVIDER"] = cfg.provider
    env["AI_MODEL"] = cfg.model
    cmd = [
        *cfg.quodeq_cmd,
        "evaluate",
        str(repo),
        "-d",
        cfg.dimensions,
        "--clean-scan",
        "-o",
        str(out),
        "--time-limit",
        str(cfg.time_limit),
        "--n-subagents",
        str(cfg.n_subagents),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-2000:]
        raise RunError(
            f"{case_dir.name}: quodeq exit code {result.returncode}\n{tail}"
        )
    evidence = find_evidence_dir(out)
    if evidence is None:
        raise RunError(f"{case_dir.name}: no evidence directory produced")
    findings, _errored = load_findings(evidence)
    return findings


def replay_case(evidence_dir: Path) -> list[Finding]:
    findings, _errored = load_findings(evidence_dir)
    return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/benchmarks/test_runner.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add benchmarks/quodeq_bench/runner.py tests/benchmarks/test_runner.py
git commit -m "feat(bench): case runner with subprocess and replay modes"
```

---

### Task 9: CLI entry point (`cli.py`, `__main__.py`)

**Files:**
- Create: `benchmarks/quodeq_bench/cli.py`, `benchmarks/quodeq_bench/__main__.py`
- Test: `tests/benchmarks/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 2–8 (exact names as declared in their Interfaces blocks).
- Produces: `main(argv: list[str] | None = None) -> int` with subcommands:
  - `run --corpus DIR --provider P --model M [--dimensions CSV] [--reps N] [--time-limit S] [--out DIR] [--replay-root DIR] [--quodeq-cmd CMD]` — for each case dir under `--corpus` (dirs containing `truth.json`): run (or replay from `<replay-root>/<case-id>/`), match, aggregate; average over reps; write `<out>/report.json`. Infrastructure failure → exit 2.
  - `compare BASELINE CANDIDATE [--threshold T]` — exit 1 with one line per regression; exit 2 if candidate has `"errored": true`; exit 0 otherwise (prints `baseline is bootstrap; gate not armed` when applicable).
  - `markdown REPORT` — print `to_markdown` output.

- [ ] **Step 1: Write the failing tests**

`tests/benchmarks/test_cli.py`:
```python
import json
from pathlib import Path

from quodeq_bench.cli import main

_EVIDENCE_LINE = {
    "t": "violation", "d": "security", "w": "hardcoded secret",
    "file": "config.py", "line": 1, "severity": "critical",
    "req": "S-CON-1", "vt": "hardcoded-secret", "refs": ["CWE-798"],
}
_TRUTH = {
    "language": "python",
    "exhaustive": True,
    "clean_files": [],
    "labels": [
        {
            "file": "config.py", "line": 1, "anchor": "API_KEY",
            "dimension": "security", "cwes": [798], "reqs": ["S-CON-1"],
            "severity": "critical", "note": "hardcoded key",
        }
    ],
}


def _corpus_with_replay(tmp_path: Path) -> tuple[Path, Path]:
    case = tmp_path / "corpus" / "py-sec-basic"
    case.mkdir(parents=True)
    (case / "config.py").write_text('API_KEY = "sk-live-x"\n', encoding="utf-8")
    (case / "truth.json").write_text(json.dumps(_TRUTH), encoding="utf-8")
    replay = tmp_path / "replay" / "py-sec-basic"
    replay.mkdir(parents=True)
    (replay / "security_evidence.jsonl").write_text(
        json.dumps(_EVIDENCE_LINE) + "\n", encoding="utf-8"
    )
    return tmp_path / "corpus", tmp_path / "replay"


def test_run_replay_writes_report(tmp_path: Path) -> None:
    corpus, replay = _corpus_with_replay(tmp_path)
    out = tmp_path / "results"
    code = main([
        "run", "--corpus", str(corpus), "--provider", "claude",
        "--model", "test", "--replay-root", str(replay), "--out", str(out),
    ])
    assert code == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["metrics"]["security"]["recall"] == 1.0
    assert report["metrics"]["security"]["precision"] == 1.0


def test_compare_exit_codes(tmp_path: Path) -> None:
    good = {"meta": {}, "errored": False,
            "metrics": {"security": {"precision": 0.9, "recall": 0.9}}}
    bad = {"meta": {}, "errored": False,
           "metrics": {"security": {"precision": 0.5, "recall": 0.9}}}
    base = tmp_path / "base.json"
    cand_ok = tmp_path / "ok.json"
    cand_bad = tmp_path / "bad.json"
    base.write_text(json.dumps(good), encoding="utf-8")
    cand_ok.write_text(json.dumps(good), encoding="utf-8")
    cand_bad.write_text(json.dumps(bad), encoding="utf-8")
    assert main(["compare", str(base), str(cand_ok)]) == 0
    assert main(["compare", str(base), str(cand_bad)]) == 1


def test_compare_errored_candidate_exits_2(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    cand = tmp_path / "cand.json"
    base.write_text(json.dumps({"bootstrap": True, "metrics": {}}), encoding="utf-8")
    cand.write_text(
        json.dumps({"meta": {}, "errored": True, "metrics": {}}), encoding="utf-8"
    )
    assert main(["compare", str(base), str(cand)]) == 2


def test_markdown_prints_table(tmp_path: Path, capsys) -> None:
    report = {"meta": {"provider": "p", "model": "m"}, "errored": False,
              "metrics": {"security": {
                  "precision": 0.9, "recall": 0.8, "f1": 0.85,
                  "fp_density": 0.1, "total_labels": 4}}}
    path = tmp_path / "r.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert main(["markdown", str(path)]) == 0
    assert "| security |" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/benchmarks/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `cli.py` and `__main__.py`**

`benchmarks/quodeq_bench/cli.py`:
```python
"""Command-line entry point: run / compare / markdown."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from quodeq_bench.compare import compare_reports
from quodeq_bench.matcher import match_case
from quodeq_bench.metrics import aggregate, count_kloc
from quodeq_bench.models import load_truth
from quodeq_bench.report import (
    average_reports,
    build_report,
    collect_meta,
    load_report,
    to_markdown,
    write_report,
)
from quodeq_bench.runner import RunConfig, RunError, replay_case, run_case

_ALL_DIMENSIONS = "security,reliability,maintainability,performance,flexibility,usability"


def _case_dirs(corpus: Path) -> list[Path]:
    return sorted(p.parent for p in corpus.glob("*/truth.json"))


def _run(args: argparse.Namespace) -> int:
    corpus = Path(args.corpus)
    cases = _case_dirs(corpus)
    if not cases:
        print(f"no cases found under {corpus}", file=sys.stderr)
        return 2
    cfg = RunConfig(
        provider=args.provider,
        model=args.model,
        dimensions=args.dimensions,
        time_limit=args.time_limit,
        quodeq_cmd=tuple(args.quodeq_cmd.split()),
    )
    repo_root = Path.cwd()
    rep_reports: list[dict] = []
    for rep in range(args.reps):
        matches, klocs = [], []
        for case_dir in cases:
            truth = load_truth(case_dir)
            try:
                if args.replay_root:
                    findings = replay_case(Path(args.replay_root) / case_dir.name)
                else:
                    with tempfile.TemporaryDirectory() as tmp:
                        findings = run_case(case_dir, cfg, Path(tmp))
            except RunError as exc:
                print(f"ERRORED: {exc}", file=sys.stderr)
                meta = collect_meta(repo_root, args.provider, args.model, args.reps)
                write_report(
                    Path(args.out) / "report.json",
                    build_report(meta, {}, errored=True),
                )
                return 2
            matches.append(match_case(truth, findings))
            klocs.append(count_kloc(case_dir, truth.language))
            print(f"rep {rep + 1}/{args.reps} case {case_dir.name}: "
                  f"{len(findings)} findings", file=sys.stderr)
        metrics = aggregate(matches, klocs)
        meta = collect_meta(repo_root, args.provider, args.model, args.reps)
        rep_reports.append(build_report(meta, metrics))
    final = average_reports(rep_reports)
    write_report(Path(args.out) / "report.json", final)
    print(to_markdown(final))
    return 0


def _compare(args: argparse.Namespace) -> int:
    baseline = load_report(Path(args.baseline))
    candidate = load_report(Path(args.candidate))
    if candidate.get("errored"):
        print("candidate run errored (infrastructure failure)", file=sys.stderr)
        return 2
    if baseline.get("bootstrap"):
        print("baseline is bootstrap; gate not armed")
        return 0
    regressions = compare_reports(baseline, candidate, args.threshold)
    for r in regressions:
        print(f"REGRESSION {r.dimension}.{r.metric}: "
              f"{r.baseline} -> {r.candidate}", file=sys.stderr)
    return 1 if regressions else 0


def _markdown(args: argparse.Namespace) -> int:
    print(to_markdown(load_report(Path(args.report))))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quodeq_bench")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run the corpus and write report.json")
    run_p.add_argument("--corpus", required=True)
    run_p.add_argument("--provider", required=True)
    run_p.add_argument("--model", required=True)
    run_p.add_argument("--dimensions", default=_ALL_DIMENSIONS)
    run_p.add_argument("--reps", type=int, default=1)
    run_p.add_argument("--time-limit", type=int, default=900)
    run_p.add_argument("--out", default="benchmarks/results/local")
    run_p.add_argument("--replay-root", default=None)
    run_p.add_argument("--quodeq-cmd", default="quodeq")
    run_p.set_defaults(func=_run)

    cmp_p = sub.add_parser("compare", help="compare candidate vs baseline")
    cmp_p.add_argument("baseline")
    cmp_p.add_argument("candidate")
    cmp_p.add_argument("--threshold", type=float, default=0.05)
    cmp_p.set_defaults(func=_compare)

    md_p = sub.add_parser("markdown", help="render a report as markdown")
    md_p.add_argument("report")
    md_p.set_defaults(func=_markdown)

    args = parser.parse_args(argv)
    return int(args.func(args))
```

`benchmarks/quodeq_bench/__main__.py`:
```python
import sys

from quodeq_bench.cli import main

sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/benchmarks/test_cli.py -q`
Expected: 4 passed

- [ ] **Step 5: Run the whole harness suite**

Run: `uv run pytest tests/benchmarks/ -q`
Expected: all passed (≈29 tests)

- [ ] **Step 6: Commit**

```bash
git add benchmarks/quodeq_bench/cli.py benchmarks/quodeq_bench/__main__.py tests/benchmarks/test_cli.py
git commit -m "feat(bench): CLI with run, compare, and markdown subcommands"
```

---

### Task 10: Corpus integrity test + first two cases (py-security, py-reliability)

**Files:**
- Create: `tests/benchmarks/test_corpus_integrity.py`
- Create: `benchmarks/corpus/synthetic/py-security/` (app.py, config.py, crypto_util.py, storage.py, truth.json)
- Create: `benchmarks/corpus/synthetic/py-reliability/` (worker.py, client.py, tempfile_io.py, pipeline.py, truth.json)

**Interfaces:**
- Consumes: `load_truth`, `DIMENSIONS` from `quodeq_bench.models`; `normalize_path` from `quodeq_bench.matcher`.
- Produces: the integrity test that all later corpus tasks must keep green. It asserts, for every `benchmarks/corpus/synthetic/*/truth.json`: it loads via `load_truth`; every labeled/clean file exists; every label line is within the file; every `anchor` substring occurs on its labeled line.

- [ ] **Step 1: Write the integrity test (fails: no corpus yet)**

`tests/benchmarks/test_corpus_integrity.py`:
```python
from pathlib import Path

import pytest

from quodeq_bench.models import load_truth

_CORPUS = Path(__file__).resolve().parents[2] / "benchmarks" / "corpus" / "synthetic"


def _cases() -> list[Path]:
    return sorted(p.parent for p in _CORPUS.glob("*/truth.json"))


def test_corpus_is_not_empty() -> None:
    assert _cases(), f"no synthetic cases under {_CORPUS}"


@pytest.mark.parametrize("case_dir", _cases(), ids=lambda p: p.name)
def test_case_integrity(case_dir: Path) -> None:
    truth = load_truth(case_dir)
    for clean in truth.clean_files:
        assert (case_dir / clean).is_file(), f"clean file missing: {clean}"
    for label in truth.labels:
        target = case_dir / label.file
        assert target.is_file(), f"label file missing: {label.file}"
        lines = target.read_text(encoding="utf-8").splitlines()
        assert label.line <= len(lines), (
            f"{label.file}:{label.line} beyond EOF ({len(lines)} lines)"
        )
        if label.anchor:
            assert label.anchor in lines[label.line - 1], (
                f"{label.file}:{label.line} anchor {label.anchor!r} not on line: "
                f"{lines[label.line - 1]!r}"
            )
```

Run: `uv run pytest tests/benchmarks/test_corpus_integrity.py -q`
Expected: FAIL (`test_corpus_is_not_empty` — no cases yet)

- [ ] **Step 2: Author `py-security`**

`benchmarks/corpus/synthetic/py-security/app.py`:
```python
import sqlite3
import subprocess

from flask import Flask, request

app = Flask(__name__)


@app.route("/user")
def get_user():
    user_id = request.args.get("id", "")
    conn = sqlite3.connect("users.db")
    query = f"SELECT * FROM users WHERE id = {user_id}"
    rows = conn.execute(query).fetchall()
    conn.close()
    return {"rows": [list(r) for r in rows]}


@app.route("/ping")
def ping():
    host = request.args.get("host", "localhost")
    output = subprocess.check_output("ping -c 1 " + host, shell=True)
    return {"output": output.decode()}
```

`benchmarks/corpus/synthetic/py-security/config.py`:
```python
API_KEY = "sk-live-9f8e7d6c5b4a3210fedcba98"
DB_PASSWORD = "SuperSecret123!"

DB_HOST = "localhost"
DB_NAME = "users"
```

`benchmarks/corpus/synthetic/py-security/crypto_util.py`:
```python
import hashlib


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()
```

`benchmarks/corpus/synthetic/py-security/storage.py`:
```python
import sqlite3


def fetch_user(conn: sqlite3.Connection, user_id: int) -> list[tuple]:
    cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchall()
```

`benchmarks/corpus/synthetic/py-security/truth.json`:
```json
{
  "language": "python",
  "exhaustive": true,
  "clean_files": ["storage.py"],
  "labels": [
    {"file": "app.py", "line": 13, "anchor": "f\"SELECT * FROM users",
     "dimension": "security", "cwes": [89, 564], "reqs": [],
     "severity": "critical", "note": "SQL injection via f-string"},
    {"file": "app.py", "line": 22, "anchor": "shell=True",
     "dimension": "security", "cwes": [78, 77], "reqs": [],
     "severity": "critical", "note": "command injection via shell=True"},
    {"file": "config.py", "line": 1, "end_line": 2, "anchor": "API_KEY = \"sk-live",
     "dimension": "security", "cwes": [798], "reqs": ["S-CON-1"],
     "severity": "critical", "note": "hardcoded credentials"},
    {"file": "crypto_util.py", "line": 5, "anchor": "hashlib.md5",
     "dimension": "security", "cwes": [327, 328, 916], "reqs": [],
     "severity": "major", "note": "weak hash for passwords"}
  ]
}
```

- [ ] **Step 3: Author `py-reliability`**

`benchmarks/corpus/synthetic/py-reliability/worker.py`:
```python
import json


def process_queue(items: list[str]) -> list[dict]:
    results = []
    for item in items:
        try:
            results.append(json.loads(item))
        except:
            pass
    return results
```

`benchmarks/corpus/synthetic/py-reliability/client.py`:
```python
import requests


def fetch_status(url: str) -> int:
    response = requests.get(url)
    return response.status_code


def fetch_until_ok(url: str) -> int:
    while True:
        code = fetch_status(url)
        if code == 200:
            return code
```

`benchmarks/corpus/synthetic/py-reliability/tempfile_io.py`:
```python
def read_config(path: str) -> str:
    handle = open(path)
    data = handle.read()
    return data
```

`benchmarks/corpus/synthetic/py-reliability/pipeline.py`:
```python
import json
import logging

logger = logging.getLogger(__name__)


def load_records(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not load %s: %s", path, exc)
        return []
```

`benchmarks/corpus/synthetic/py-reliability/truth.json`:
```json
{
  "language": "python",
  "exhaustive": true,
  "clean_files": ["pipeline.py"],
  "labels": [
    {"file": "worker.py", "line": 9, "anchor": "except:",
     "dimension": "reliability", "cwes": [703, 396, 390], "reqs": [],
     "severity": "major", "note": "bare except swallows all errors"},
    {"file": "client.py", "line": 5, "anchor": "requests.get(url)",
     "dimension": "reliability", "cwes": [400, 1088], "reqs": [],
     "severity": "major", "note": "network call without timeout"},
    {"file": "client.py", "line": 10, "anchor": "while True:",
     "dimension": "reliability", "cwes": [835], "reqs": [],
     "severity": "major", "note": "unbounded retry loop"},
    {"file": "tempfile_io.py", "line": 2, "anchor": "open(path)",
     "dimension": "reliability", "cwes": [772, 404], "reqs": [],
     "severity": "minor", "note": "file handle never closed"}
  ]
}
```

- [ ] **Step 4: Enrich reliability labels with real requirement IDs**

List the reliability requirement ids shipped with quodeq:

Run:
```bash
uv run python -c "
import json
data = json.load(open('src/quodeq/data/standards/iso25010/reliability.json'))
def walk(node):
    if isinstance(node, dict):
        if 'id' in node and 'text' in node:
            print(node['id'], '-', node['text'][:90])
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for v in node:
            walk(v)
walk(data)
"
```

For each label in `py-reliability/truth.json`, add to its `reqs` array every printed requirement id whose text covers that violation (error/exception handling ids for the bare except; timeout/external-call ids for the missing timeout; retry/loop-bound ids for `while True`; resource-release ids for the unclosed handle). Do the same review for `py-security` (security.json) and add any id matching hardcoded credentials / injection / weak crypto. Keep the existing `cwes` untouched — labels match on either.

- [ ] **Step 5: Run integrity test**

Run: `uv run pytest tests/benchmarks/test_corpus_integrity.py -q`
Expected: PASS (1 + 2 case tests). If an anchor assertion fails, fix the `line` in truth.json to the line actually containing the anchor — the assertion message shows the offending line content.

- [ ] **Step 6: Commit**

```bash
git add benchmarks/corpus/synthetic/py-security benchmarks/corpus/synthetic/py-reliability tests/benchmarks/test_corpus_integrity.py
git commit -m "feat(bench): corpus integrity test + security and reliability cases"
```

---

### Task 11: Corpus cases for maintainability, performance, flexibility, usability

**Files:**
- Create: `benchmarks/corpus/synthetic/py-maintainability/` (orders.py, helpers.py, truth.json)
- Create: `benchmarks/corpus/synthetic/py-performance/` (report_gen.py, fetcher.py, cache.py, truth.json)
- Create: `benchmarks/corpus/synthetic/py-flexibility/` (settings.py, session_store.py, config_loader.py, truth.json)
- Create: `benchmarks/corpus/synthetic/py-usability/` (cli_tool.py, api.py, truth.json)

**Interfaces:**
- Consumes: the integrity test from Task 10 (must stay green).
- Produces: four more cases; corpus now covers all six dimensions.

- [ ] **Step 1: Author `py-maintainability`**

`benchmarks/corpus/synthetic/py-maintainability/orders.py`:
```python
def process_order(order, customer, inventory, pricing, shipping, taxes, promos, audit):
    result = {"status": "pending", "warnings": []}
    if order:
        if customer:
            if customer.get("active"):
                for item in order.get("items", []):
                    if item["sku"] in inventory:
                        if inventory[item["sku"]] >= item["qty"]:
                            price = pricing.get(item["sku"], 0)
                            if promos:
                                for promo in promos:
                                    if promo.get("sku") == item["sku"]:
                                        if promo.get("active"):
                                            price = price * (1 - promo["pct"])
                            line = price * item["qty"]
                            if taxes:
                                if customer.get("region") in taxes:
                                    line = line * (1 + taxes[customer["region"]])
                            result.setdefault("lines", []).append(line)
                        else:
                            result["warnings"].append("low stock: " + item["sku"])
                    else:
                        result["warnings"].append("unknown sku: " + item["sku"])
                if shipping:
                    if customer.get("region") in shipping:
                        result["shipping"] = shipping[customer["region"]]
                    else:
                        result["shipping"] = shipping.get("default", 0)
                result["total"] = sum(result.get("lines", [])) + result.get("shipping", 0)
                result["status"] = "priced"
                if audit is not None:
                    audit.append({"order": order.get("id"), "total": result["total"]})
            else:
                result["status"] = "inactive-customer"
        else:
            result["status"] = "missing-customer"
    else:
        result["status"] = "missing-order"
    return result
```

`benchmarks/corpus/synthetic/py-maintainability/helpers.py`:
```python
def format_currency(amount: float) -> str:
    return f"{amount:.2f} EUR"


def region_label(region: str) -> str:
    return region.strip().upper()
```

`benchmarks/corpus/synthetic/py-maintainability/truth.json`:
```json
{
  "language": "python",
  "exhaustive": true,
  "clean_files": ["helpers.py"],
  "labels": [
    {"file": "orders.py", "line": 1, "end_line": 38, "anchor": "def process_order(order, customer, inventory",
     "dimension": "maintainability", "cwes": [1121], "reqs": ["M-MOD-1"],
     "severity": "major", "note": "deeply nested, high-complexity god function"},
    {"file": "orders.py", "line": 1, "anchor": "shipping, taxes, promos, audit",
     "dimension": "maintainability", "cwes": [1064], "reqs": ["M-MOD-4"],
     "severity": "minor", "note": "8 positional parameters"}
  ]
}
```

- [ ] **Step 2: Author `py-performance`**

`benchmarks/corpus/synthetic/py-performance/report_gen.py`:
```python
import sqlite3


def order_totals(conn: sqlite3.Connection, order_ids: list[int]) -> str:
    summary = ""
    for order_id in order_ids:
        row = conn.execute(
            "SELECT total FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        summary = summary + f"{order_id}: {row[0]}\n"
    return summary
```

`benchmarks/corpus/synthetic/py-performance/fetcher.py`:
```python
import asyncio


async def fetch_one(name: str) -> str:
    await asyncio.sleep(0.1)
    return name


async def fetch_all() -> list[str]:
    first = await fetch_one("alpha")
    second = await fetch_one("beta")
    third = await fetch_one("gamma")
    return [first, second, third]


async def read_snapshot(path: str) -> str:
    with open(path) as handle:
        return handle.read()
```

`benchmarks/corpus/synthetic/py-performance/cache.py`:
```python
import asyncio


async def fetch_many(names: list[str]) -> list[str]:
    from fetcher import fetch_one

    return list(await asyncio.gather(*(fetch_one(n) for n in names)))
```

`benchmarks/corpus/synthetic/py-performance/truth.json`:
```json
{
  "language": "python",
  "exhaustive": true,
  "clean_files": ["cache.py"],
  "labels": [
    {"file": "report_gen.py", "line": 7, "end_line": 9, "anchor": "conn.execute(",
     "dimension": "performance", "cwes": [1049], "reqs": ["P-TIM-1"],
     "severity": "major", "note": "database query inside a loop (N+1)"},
    {"file": "report_gen.py", "line": 10, "anchor": "summary = summary +",
     "dimension": "performance", "cwes": [1046], "reqs": ["P-TIM-4"],
     "severity": "minor", "note": "string concatenation in a loop"},
    {"file": "fetcher.py", "line": 10, "end_line": 12, "anchor": "first = await fetch_one",
     "dimension": "performance", "cwes": [1050], "reqs": ["P-TIM-2"],
     "severity": "major", "note": "sequential awaits on independent calls"},
    {"file": "fetcher.py", "line": 17, "anchor": "with open(path)",
     "dimension": "performance", "cwes": [1050], "reqs": ["P-TIM-3"],
     "severity": "major", "note": "blocking file I/O inside async function"}
  ]
}
```

- [ ] **Step 3: Author `py-flexibility`**

`benchmarks/corpus/synthetic/py-flexibility/settings.py`:
```python
DATABASE_URL = "postgres://prod-db.internal:5432/app"
EXPORT_DIR = "/home/deploy/exports"
SMTP_HOST = "10.0.4.12"
```

`benchmarks/corpus/synthetic/py-flexibility/session_store.py`:
```python
_SESSIONS: dict[str, dict] = {}


def save_session(session_id: str, data: dict) -> None:
    _SESSIONS[session_id] = data


def load_session(session_id: str) -> dict:
    return _SESSIONS.get(session_id, {})
```

`benchmarks/corpus/synthetic/py-flexibility/config_loader.py`:
```python
import os


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///local.db")
```

`benchmarks/corpus/synthetic/py-flexibility/truth.json`:
```json
{
  "language": "python",
  "exhaustive": true,
  "clean_files": ["config_loader.py"],
  "labels": [
    {"file": "settings.py", "line": 1, "end_line": 3, "anchor": "postgres://prod-db.internal",
     "dimension": "flexibility", "cwes": [547], "reqs": ["F-ADP-1"],
     "severity": "major", "note": "environment-specific values hardcoded"},
    {"file": "session_store.py", "line": 1, "anchor": "_SESSIONS",
     "dimension": "flexibility", "cwes": [1108], "reqs": ["F-SCL-1"],
     "severity": "major", "note": "in-process session state blocks horizontal scaling"}
  ]
}
```

- [ ] **Step 4: Author `py-usability`**

`benchmarks/corpus/synthetic/py-usability/cli_tool.py`:
```python
import sys
import traceback


def main() -> int:
    args = sys.argv[1:]
    source = args[0]
    target = args[1]
    try:
        with open(source) as handle:
            data = handle.read()
        with open(target, "w") as handle:
            handle.write(data)
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`benchmarks/corpus/synthetic/py-usability/api.py`:
```python
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/convert/<amount>")
def convert(amount: str):
    if not amount.isdigit():
        return jsonify({"error": "bad input"}), 400
    return jsonify({"result": int(amount) * 100})
```

`benchmarks/corpus/synthetic/py-usability/truth.json`:
```json
{
  "language": "python",
  "exhaustive": true,
  "clean_files": [],
  "labels": [
    {"file": "cli_tool.py", "line": 6, "end_line": 8, "anchor": "args = sys.argv[1:]",
     "dimension": "usability", "cwes": [1053], "reqs": ["U-LRN-1"],
     "severity": "minor", "note": "manual argv parsing, no --help"},
    {"file": "cli_tool.py", "line": 15, "anchor": "traceback.print_exc()",
     "dimension": "usability", "cwes": [209], "reqs": ["U-APR-1"],
     "severity": "major", "note": "raw stack trace shown to end user"},
    {"file": "api.py", "line": 9, "anchor": "\"error\": \"bad input\"",
     "dimension": "usability", "cwes": [], "reqs": ["U-APR-2"],
     "severity": "minor", "note": "error response lacks machine-readable code"}
  ]
}
```

- [ ] **Step 5: Verify requirement ids exist**

For each of the four dimensions, list shipped requirement ids (same walker as Task 10 Step 4, swapping the filename to `maintainability.json`, `performance.json`, `flexibility.json`, `usability.json`). Confirm every `reqs` entry used above is printed; replace any that isn't with the closest real id (matching by text) and extend `reqs` with additional matching ids.

- [ ] **Step 6: Run integrity test**

Run: `uv run pytest tests/benchmarks/test_corpus_integrity.py -q`
Expected: PASS (1 + 6 case tests). Fix any anchor/line mismatch the assertion reports.

- [ ] **Step 7: Commit**

```bash
git add benchmarks/corpus/synthetic/py-maintainability benchmarks/corpus/synthetic/py-performance benchmarks/corpus/synthetic/py-flexibility benchmarks/corpus/synthetic/py-usability
git commit -m "feat(bench): corpus cases for maintainability, performance, flexibility, usability"
```

---

### Task 12: JavaScript corpus cases

**Files:**
- Create: `benchmarks/corpus/synthetic/js-security/` (server.js, config.js, db.js, truth.json)
- Create: `benchmarks/corpus/synthetic/js-maintainability/` (report.js, format.js, truth.json)

**Interfaces:**
- Consumes: integrity test from Task 10 (must stay green).
- Produces: corpus meets the spec's "Python plus one other language" requirement (8 cases total).

- [ ] **Step 1: Author `js-security`**

`benchmarks/corpus/synthetic/js-security/server.js`:
```javascript
const express = require("express");
const sqlite3 = require("sqlite3");

const app = express();
const db = new sqlite3.Database("users.db");

app.get("/user", (req, res) => {
  const query = `SELECT * FROM users WHERE id = ${req.query.id}`;
  db.all(query, (err, rows) => res.json(rows));
});

app.get("/calc", (req, res) => {
  const result = eval(req.query.expr);
  res.json({ result });
});
```

`benchmarks/corpus/synthetic/js-security/config.js`:
```javascript
module.exports = {
  apiKey: "sk-live-11223344556677889900aabb",
  dbPassword: "Sup3rS3cret!",
};
```

`benchmarks/corpus/synthetic/js-security/db.js`:
```javascript
function fetchUser(db, userId, callback) {
  db.all("SELECT * FROM users WHERE id = ?", [userId], callback);
}

module.exports = { fetchUser };
```

`benchmarks/corpus/synthetic/js-security/truth.json`:
```json
{
  "language": "javascript",
  "exhaustive": true,
  "clean_files": ["db.js"],
  "labels": [
    {"file": "server.js", "line": 8, "anchor": "SELECT * FROM users WHERE id = ${",
     "dimension": "security", "cwes": [89, 564], "reqs": [],
     "severity": "critical", "note": "SQL injection via template literal"},
    {"file": "server.js", "line": 13, "anchor": "eval(req.query.expr)",
     "dimension": "security", "cwes": [95, 94], "reqs": [],
     "severity": "critical", "note": "eval of user input"},
    {"file": "config.js", "line": 2, "end_line": 3, "anchor": "apiKey: \"sk-live",
     "dimension": "security", "cwes": [798], "reqs": ["S-CON-1"],
     "severity": "critical", "note": "hardcoded credentials"}
  ]
}
```

- [ ] **Step 2: Author `js-maintainability`**

`benchmarks/corpus/synthetic/js-maintainability/report.js`:
```javascript
function buildReport(orders, customers, taxes, shipping, promos, locale, currency, audit, verbose) {
  const lines = [];
  for (const order of orders) {
    const customer = customers[order.customerId];
    if (customer) {
      if (customer.active) {
        let total = 0;
        for (const item of order.items) {
          let price = item.price * item.qty;
          if (promos && promos[item.sku]) {
            if (promos[item.sku].active) {
              price = price * (1 - promos[item.sku].pct);
            }
          }
          if (taxes && taxes[customer.region]) {
            price = price * (1 + taxes[customer.region]);
          }
          total += price;
        }
        if (shipping && shipping[customer.region]) {
          total += shipping[customer.region];
        }
        if (verbose) {
          lines.push(`${customer.name} (${locale}/${currency}): ${total}`);
        } else {
          lines.push(`${customer.name}: ${total}`);
        }
        if (audit) {
          audit.push({ order: order.id, total });
        }
      }
    }
  }
  return lines.join("\n");
}

module.exports = { buildReport };
```

`benchmarks/corpus/synthetic/js-maintainability/format.js`:
```javascript
function formatCurrency(amount, currency) {
  return `${amount.toFixed(2)} ${currency}`;
}

module.exports = { formatCurrency };
```

`benchmarks/corpus/synthetic/js-maintainability/truth.json`:
```json
{
  "language": "javascript",
  "exhaustive": true,
  "clean_files": ["format.js"],
  "labels": [
    {"file": "report.js", "line": 1, "end_line": 36, "anchor": "function buildReport(orders",
     "dimension": "maintainability", "cwes": [1121], "reqs": ["M-MOD-1"],
     "severity": "major", "note": "high-complexity nested report builder"},
    {"file": "report.js", "line": 1, "anchor": "locale, currency, audit, verbose",
     "dimension": "maintainability", "cwes": [1064], "reqs": ["M-MOD-4"],
     "severity": "minor", "note": "9 positional parameters"}
  ]
}
```

- [ ] **Step 3: Run integrity test**

Run: `uv run pytest tests/benchmarks/test_corpus_integrity.py -q`
Expected: PASS (1 + 8 case tests). Fix any anchor/line mismatch reported.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/benchmarks/ -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add benchmarks/corpus/synthetic/js-security benchmarks/corpus/synthetic/js-maintainability
git commit -m "feat(bench): JavaScript corpus cases"
```

---

### Task 13: CI gate workflow + bootstrap baseline

**Files:**
- Create: `benchmarks/baselines/gate.json`
- Create: `.github/workflows/benchmark.yml`
- Modify: `benchmarks/README.md` (baseline update instructions)

**Interfaces:**
- Consumes: CLI from Task 9 (`run`, `compare` semantics and exit codes); `compare_reports` bootstrap behavior from Task 7.
- Produces: a PR-gating workflow. Until a real baseline is committed, the workflow runs the benchmark and reports, but `compare` exits 0 (bootstrap).

- [ ] **Step 1: Bootstrap baseline**

`benchmarks/baselines/gate.json`:
```json
{
  "bootstrap": true,
  "provider": "claude",
  "model": "claude-haiku-4-5-20251001",
  "threshold": 0.05,
  "metrics": {}
}
```

- [ ] **Step 2: Workflow**

`.github/workflows/benchmark.yml`:
```yaml
name: Benchmark gate

on:
  pull_request:
    paths:
      - "src/quodeq/data/prompts/**"
      - "src/quodeq/data/standards/**"
      - "src/quodeq/analysis/**"
      - "benchmarks/**"

jobs:
  gate:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v7.0.0
      - name: Install uv
        uses: astral-sh/setup-uv@v8.3.0
      - name: Set up Python
        run: uv python install 3.13
      - name: Install dependencies
        run: uv sync
      - name: Install claude CLI
        run: npm install -g @anthropic-ai/claude-code
      - name: Read pinned model from baseline
        id: baseline
        run: echo "model=$(uv run python -c "import json; print(json.load(open('benchmarks/baselines/gate.json'))['model'])")" >> "$GITHUB_OUTPUT"
      - name: Run benchmark (2 reps)
        env:
          ANTHROPIC_API_KEY: ${{ secrets.BENCHMARK_ANTHROPIC_API_KEY }}
          PYTHONPATH: benchmarks
        run: |
          uv run python -m quodeq_bench run \
            --corpus benchmarks/corpus/synthetic \
            --provider claude \
            --model "${{ steps.baseline.outputs.model }}" \
            --reps 2 \
            --out benchmarks/results/gate
      - name: Compare against baseline
        env:
          PYTHONPATH: benchmarks
        run: |
          uv run python -m quodeq_bench compare \
            benchmarks/baselines/gate.json \
            benchmarks/results/gate/report.json \
            --threshold 0.05
      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-report
          path: benchmarks/results/gate/report.json
```

- [ ] **Step 3: Document baseline arming in `benchmarks/README.md`**

Append:
```markdown
## Arming the gate

The committed `baselines/gate.json` starts as `"bootstrap": true` (compare
always passes). To arm it: take the `report.json` from a green CI run (or a
local run with the pinned model), copy its `metrics` object into
`gate.json`, remove the `bootstrap` key, and commit. When a PR legitimately
improves metrics, refresh the baseline the same way in that PR.

The `BENCHMARK_ANTHROPIC_API_KEY` repository secret must be set for the
workflow to run.
```

- [ ] **Step 4: Validate workflow syntax and full suite**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/benchmark.yml').read_text()); print('workflow ok')"`
Expected: `workflow ok` (pyyaml is available transitively; if not, `uvx --from pyyaml python` equivalent or rely on GitHub's validation).

Run: `uv run pytest tests/benchmarks/ -q && uv run pytest tests/ -q --co -m "not integration" | tail -2`
Expected: benchmarks suite passes; full collection still clean.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/baselines/gate.json .github/workflows/benchmark.yml benchmarks/README.md
git commit -m "ci: benchmark regression gate with bootstrap baseline"
```

---

### Task 14: End-to-end replay smoke test + PR

**Files:**
- Create: `tests/benchmarks/test_e2e_replay.py`
- Create: `tests/benchmarks/fixtures/replay/py-security/security_evidence.jsonl`

**Interfaces:**
- Consumes: the real corpus (Task 10) and the CLI (Task 9).
- Produces: a token-free end-to-end test proving corpus → replay → match → report → compare works as one pipeline.

- [ ] **Step 1: Create the recorded-evidence fixture**

`tests/benchmarks/fixtures/replay/py-security/security_evidence.jsonl` (three lines that should match three of the four py-security labels, plus one FP):
```
{"schema_version": 1, "p": "Confidentiality", "t": "violation", "d": "security", "w": "SQL injection", "file": "app.py", "line": 13, "snippet": "query = f\"SELECT * FROM users WHERE id = {user_id}\"", "severity": "critical", "reason": "user input in SQL", "req": "S-CON-1", "vt": "sql-injection", "refs": ["CWE-89"]}
{"schema_version": 1, "p": "Confidentiality", "t": "violation", "d": "security", "w": "Command injection", "file": "app.py", "line": 22, "snippet": "subprocess.check_output(\"ping -c 1 \" + host, shell=True)", "severity": "critical", "reason": "user input in shell", "req": "S-CON-1", "vt": "command-injection", "refs": ["CWE-78"]}
{"schema_version": 1, "p": "Confidentiality", "t": "violation", "d": "security", "w": "Hardcoded key", "file": "config.py", "line": 1, "snippet": "API_KEY = \"sk-live-9f8e7d6c5b4a3210fedcba98\"", "severity": "critical", "reason": "secret in source", "req": "S-CON-1", "vt": "hardcoded-secret", "refs": ["CWE-798"]}
{"schema_version": 1, "p": "Confidentiality", "t": "violation", "d": "security", "w": "Spurious finding", "file": "storage.py", "line": 5, "snippet": "cursor = conn.execute(...)", "severity": "minor", "reason": "not actually a problem", "req": "S-CON-2", "vt": "spurious", "refs": ["CWE-999"]}
```

- [ ] **Step 2: Write the e2e test**

`tests/benchmarks/test_e2e_replay.py`:
```python
import json
import shutil
from pathlib import Path

from quodeq_bench.cli import main

_ROOT = Path(__file__).resolve().parents[2]
_CASE = _ROOT / "benchmarks" / "corpus" / "synthetic" / "py-security"
_FIXTURE = Path(__file__).parent / "fixtures" / "replay" / "py-security"


def test_replay_pipeline_end_to_end(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    (corpus / "py-security").parent.mkdir(parents=True)
    shutil.copytree(_CASE, corpus / "py-security")
    replay = tmp_path / "replay"
    shutil.copytree(_FIXTURE, replay / "py-security")
    out = tmp_path / "results"

    code = main([
        "run", "--corpus", str(corpus), "--provider", "claude",
        "--model", "replay", "--replay-root", str(replay), "--out", str(out),
    ])
    assert code == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    sec = report["metrics"]["security"]
    assert sec["total_labels"] == 4
    assert sec["matched_labels"] == 3
    assert sec["recall"] == 0.75
    assert sec["fp"] == 1
    assert sec["precision"] == 0.75
```

- [ ] **Step 3: Run it**

Run: `uv run pytest tests/benchmarks/test_e2e_replay.py -q`
Expected: 1 passed

- [ ] **Step 4: Full verification**

Run: `uv run pytest tests/ -q --tb=short -m "not integration"`
Expected: full repo suite passes (coverage gate measures `quodeq`, not `quodeq_bench`, so it is unaffected).

- [ ] **Step 5: Commit and open PR**

```bash
git add tests/benchmarks/test_e2e_replay.py tests/benchmarks/fixtures/
git commit -m "test(bench): end-to-end replay smoke test"
git push -u origin feat/benchmark-harness
gh pr create --base develop --title "Accuracy benchmark harness (Phase 1)" --body "$(cat <<'EOF'
Adds the benchmark harness from docs/superpowers/specs/2026-07-10-accuracy-benchmark-harness-design.md:

- benchmarks/quodeq_bench: black-box runner, evidence parser, label matcher, per-dimension precision/recall metrics, report + markdown, baseline compare
- Synthetic corpus: 8 cases covering all 6 ISO 25010 dimensions (Python + JavaScript), self-validating truth.json labels (anchor check in tests)
- CI gate: .github/workflows/benchmark.yml runs the corpus on pinned Haiku (2 reps) for PRs touching prompts/analysis/standards; compares against benchmarks/baselines/gate.json (bootstrap until armed)
- Token-free test suite: matcher/metrics/report/compare unit tests + fake-subprocess runner test + end-to-end replay test

Requires the BENCHMARK_ANTHROPIC_API_KEY repo secret before the gate produces real numbers. Arming instructions in benchmarks/README.md.
EOF
)"
```

---

## Post-merge follow-ups (not in this plan)

1. Arm the baseline: one green CI (or local) run with the pinned model, copy metrics into `benchmarks/baselines/gate.json`, drop `bootstrap`.
2. Phase 2: `benchmarks/corpus/external.json` + fetcher + published per-model report.
3. Phase 3: variance measurement (5× reps, error bars in markdown).
