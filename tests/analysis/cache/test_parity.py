"""V1 vs V2 parity tests — the cache layer must be observationally
equivalent to the legacy fingerprint+JSONL+carry-forward path.

Strategy: build a synthetic pipeline that uses the *real* V1 helpers
(`classify_files`, `carry_forward_findings`, `build_fingerprint`) and the
*real* V2 primitive (`analyze_unit`), wired with a shared deterministic
dispatcher so every divergence is attributable to layering, not LLM
nondeterminism.

The properties we pin down:

  - cold-start parity: same files dispatched, same findings
  - no-change parity: zero new dispatches, V1 carries forward, V2 hits
  - partial-change parity: only changed files dispatch, rest reused
  - standards-change parity: both paths full-re-analyse
  - dispatch counts match across multi-run sequences

These tests do not exercise the live pipeline (subagent pool, API
runner). They prove the *layering* is sound — that swapping
fingerprint+carry-forward for cache lookups produces equivalent output
given the same dispatcher behaviour.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from quodeq.analysis.cache import (
    LocalFileBackend,
    WorkUnit,
    DispatchResult,
    analyze_unit,
)
from quodeq.analysis.fingerprint import _hash_standards, build_fingerprint
from quodeq.analysis.incremental import (
    ClassificationInput,
    classify_files,
)
from quodeq.analysis._incr_carry_forward import carry_forward_findings


# ============================================================
# Synthetic project + deterministic dispatcher
# ============================================================


@dataclass
class SyntheticProject:
    """A project on disk plus the metadata needed to key its work units."""

    src: Path
    files: list[str]
    dimension: str = "security"
    standards_dir: Path | None = None
    _standards_hash_override: str = "s" * 64
    prompts_hash: str = "p" * 64
    evaluator_hash: str = "e" * 64
    model_id: str = "test-model"
    language: str = "python"

    @property
    def standards_hash(self) -> str:
        """Derive from disk when a real standards_dir is set, else use override.

        This keeps V1 (reads from disk) and V2 (uses cache key field) in
        agreement — both consult the same underlying source.
        """
        if self.standards_dir is None:
            return self._standards_hash_override
        h = _hash_standards(self.standards_dir, self.dimension)
        return h or self._standards_hash_override

    def file_content(self, name: str) -> str:
        return (self.src / name).read_text()

    def file_content_hash(self, name: str) -> str:
        return hashlib.sha256(self.file_content(name).encode()).hexdigest()


def _make_project(
    tmp_path: Path,
    contents: dict[str, str],
    *,
    standards_text: str | None = None,
    **overrides,
) -> SyntheticProject:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for name, text in contents.items():
        (src / name).write_text(text)
    standards_dir = None
    if standards_text is not None:
        standards_dir = tmp_path / "standards"
        compiled = standards_dir / "compiled"
        compiled.mkdir(parents=True, exist_ok=True)
        dim = overrides.get("dimension", "security")
        (compiled / f"{dim}.json").write_text(standards_text)
    return SyntheticProject(
        src=src, files=sorted(contents.keys()),
        standards_dir=standards_dir, **overrides,
    )


@dataclass
class DispatchRecorder:
    """Deterministic dispatcher that records calls.

    Findings are derived from file content so two runs with the same
    inputs produce identical findings — this is what makes
    byte-equal parity assertions possible without a real LLM.
    """

    project: SyntheticProject
    calls: list[str] = field(default_factory=list)

    def for_file(self, file_path: str) -> list[dict]:
        content = self.project.file_content(file_path)
        h = hashlib.sha256(content.encode()).hexdigest()[:8]
        # Two findings per file so we can detect order/preservation issues.
        return [
            {"file": file_path, "line": 1, "t": "violation", "w": f"v-{h}"},
            {"file": file_path, "line": 2, "t": "compliance", "w": f"c-{h}"},
        ]

    # V1 boundary: dispatched by file_path.
    def dispatch_for_v1(self, file_path: str) -> list[dict]:
        self.calls.append(file_path)
        return self.for_file(file_path)

    # V2 boundary: dispatched by WorkUnit (Dispatcher Protocol).
    def dispatch_for_v2(self, unit: WorkUnit) -> DispatchResult:
        self.calls.append(unit.file_path)
        return DispatchResult(findings=self.for_file(unit.file_path), files_read=1)


# ============================================================
# Synthetic V1 pipeline using REAL V1 helpers
# ============================================================


@dataclass
class V1RunResult:
    findings: list[dict]
    dispatched: list[str]
    fingerprint: dict


def run_v1(
    project: SyntheticProject,
    *,
    work_dir: Path,
    prev_fingerprint: dict | None = None,
    prev_jsonl: Path | None = None,
    recorder: DispatchRecorder,
) -> V1RunResult:
    """Synthetic V1 orchestration: classify → carry-forward → dispatch → save fingerprint."""
    work_dir.mkdir(parents=True, exist_ok=True)
    output_jsonl = work_dir / f"{project.dimension}_evidence.jsonl"
    if output_jsonl.exists():
        output_jsonl.unlink()

    classification = classify_files(inputs=ClassificationInput(
        src=project.src, files=project.files,
        prev_fingerprint=prev_fingerprint, standards_dir=project.standards_dir,
        dimension=project.dimension, language=project.language,
    ))

    if prev_jsonl and classification.unchanged:
        carry_forward_findings(prev_jsonl, output_jsonl, classification.unchanged)

    dispatched_in_this_run: list[str] = []
    with output_jsonl.open("a") as out:
        for f in classification.to_analyze:
            for finding in recorder.dispatch_for_v1(f):
                out.write(json.dumps(finding) + "\n")
            dispatched_in_this_run.append(f)

    fingerprint = build_fingerprint(
        project.src, project.files, project.dimension,
        standards_dir=project.standards_dir,
        analyzed_files=set(project.files),  # post-#427 contract
    )

    return V1RunResult(
        findings=_read_jsonl(output_jsonl),
        dispatched=dispatched_in_this_run,
        fingerprint=fingerprint,
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ============================================================
# Synthetic V2 pipeline using REAL analyze_unit
# ============================================================


@dataclass
class V2RunResult:
    findings: list[dict]
    dispatched: list[str]


def run_v2(
    project: SyntheticProject,
    *,
    cache: LocalFileBackend,
    recorder: DispatchRecorder,
) -> V2RunResult:
    """Synthetic V2 orchestration: per-file analyze_unit, aggregate findings."""
    findings: list[dict] = []
    dispatched_before = list(recorder.calls)
    for f in project.files:
        unit = WorkUnit(
            file_path=f,
            file_content_hash=project.file_content_hash(f),
            dimension=project.dimension,
            standards_hash=project.standards_hash,
            prompts_hash=project.prompts_hash,
            evaluator_hash=project.evaluator_hash,
            model_id=project.model_id,
            language=project.language,
        )
        result = analyze_unit(unit, cache=cache, dispatcher=recorder.dispatch_for_v2)
        findings.extend(result.entry.findings)
    dispatched_in_this_run = recorder.calls[len(dispatched_before):]
    return V2RunResult(findings=findings, dispatched=dispatched_in_this_run)


# ============================================================
# Parity assertions
# ============================================================


def _normalize(findings: list[dict]) -> list[dict]:
    """Order-insensitive comparison key."""
    return sorted(findings, key=lambda f: (f.get("file", ""), f.get("line", 0), f.get("t", "")))


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache_v2")


# ---------- cold start ----------

class TestColdStartParity:
    def test_no_prior_state_dispatches_all_files(self, tmp_path: Path, cache: LocalFileBackend):
        project = _make_project(tmp_path, {
            "auth.py": "def login(): pass",
            "utils.py": "def helper(): pass",
        })
        v1_recorder = DispatchRecorder(project=project)
        v2_recorder = DispatchRecorder(project=project)

        v1 = run_v1(project, work_dir=tmp_path / "v1", recorder=v1_recorder)
        v2 = run_v2(project, cache=cache, recorder=v2_recorder)

        assert sorted(v1.dispatched) == sorted(v2.dispatched) == project.files
        assert _normalize(v1.findings) == _normalize(v2.findings)


# ---------- no-change second run ----------

class TestNoChangeParity:
    def test_second_run_dispatches_zero_files_in_both(self, tmp_path: Path, cache: LocalFileBackend):
        project = _make_project(tmp_path, {
            "auth.py": "def login(): pass",
            "utils.py": "def helper(): pass",
        })
        v1_recorder = DispatchRecorder(project=project)
        v2_recorder = DispatchRecorder(project=project)

        # Run 1: cold start (populates cache + JSONL).
        run1_v1 = run_v1(project, work_dir=tmp_path / "v1_run1", recorder=v1_recorder)
        run1_v2 = run_v2(project, cache=cache, recorder=v2_recorder)

        # Run 2: no changes — V1 carries forward, V2 hits cache.
        v1_recorder.calls.clear()
        v2_recorder.calls.clear()
        run2_v1 = run_v1(
            project, work_dir=tmp_path / "v1_run2",
            prev_fingerprint=run1_v1.fingerprint,
            prev_jsonl=tmp_path / "v1_run1" / f"{project.dimension}_evidence.jsonl",
            recorder=v1_recorder,
        )
        run2_v2 = run_v2(project, cache=cache, recorder=v2_recorder)

        # The structural property: zero new dispatches in either path.
        assert run2_v1.dispatched == []
        assert run2_v2.dispatched == []

        # And the findings are identical to run 1's output.
        assert _normalize(run2_v1.findings) == _normalize(run1_v1.findings)
        assert _normalize(run2_v2.findings) == _normalize(run1_v2.findings)
        assert _normalize(run2_v1.findings) == _normalize(run2_v2.findings)


# ---------- partial change ----------

class TestPartialChangeParity:
    def test_only_changed_file_dispatches(self, tmp_path: Path, cache: LocalFileBackend):
        project = _make_project(tmp_path, {
            "auth.py": "def login(): pass",
            "utils.py": "def helper(): pass",
            "routes.py": "def route(): pass",
        })
        v1_recorder = DispatchRecorder(project=project)
        v2_recorder = DispatchRecorder(project=project)

        # Run 1: cold start.
        run1_v1 = run_v1(project, work_dir=tmp_path / "v1_run1", recorder=v1_recorder)
        run_v2(project, cache=cache, recorder=v2_recorder)

        # Modify auth.py only.
        (project.src / "auth.py").write_text("def login(): secure()")

        v1_recorder.calls.clear()
        v2_recorder.calls.clear()

        run2_v1 = run_v1(
            project, work_dir=tmp_path / "v1_run2",
            prev_fingerprint=run1_v1.fingerprint,
            prev_jsonl=tmp_path / "v1_run1" / f"{project.dimension}_evidence.jsonl",
            recorder=v1_recorder,
        )
        run2_v2 = run_v2(project, cache=cache, recorder=v2_recorder)

        # Only auth.py should be re-dispatched in either path.
        assert run2_v1.dispatched == ["auth.py"]
        assert run2_v2.dispatched == ["auth.py"]

        # Final findings include all three files; new content for auth.py,
        # carried-forward / cached for the others.
        assert _normalize(run2_v1.findings) == _normalize(run2_v2.findings)
        files_in_v2 = {f["file"] for f in run2_v2.findings}
        assert files_in_v2 == set(project.files)


# ---------- standards change → full re-analysis ----------

class TestStandardsChangeParity:
    def test_standards_change_redispatches_everything_in_both(self, tmp_path: Path, cache: LocalFileBackend):
        """Standards modification → V1 returns full_reanalysis=True; V2's
        cache key changes (standards_hash component) so every entry misses.
        Both end up re-dispatching every file."""
        project = _make_project(
            tmp_path, {"a.py": "x = 1", "b.py": "y = 2"},
            standards_text='{"version": 1}',
        )
        v1_recorder = DispatchRecorder(project=project)
        v2_recorder = DispatchRecorder(project=project)

        # Run 1: cold start under standards v1.
        r1_v1 = run_v1(project, work_dir=tmp_path / "v1_run1", recorder=v1_recorder)
        run_v2(project, cache=cache, recorder=v2_recorder)
        assert sorted(r1_v1.dispatched) == sorted(project.files)

        # Modify standards on disk. Both V1 (reads from standards_dir) and
        # V2 (standards_hash on the WorkUnit derives from the same source
        # via the SyntheticProject property) observe the change.
        compiled = project.standards_dir / "compiled" / f"{project.dimension}.json"
        compiled.write_text('{"version": 2}')

        v1_recorder.calls.clear()
        v2_recorder.calls.clear()

        r2_v1 = run_v1(
            project, work_dir=tmp_path / "v1_run2",
            prev_fingerprint=r1_v1.fingerprint,
            prev_jsonl=tmp_path / "v1_run1" / f"{project.dimension}_evidence.jsonl",
            recorder=v1_recorder,
        )
        r2_v2 = run_v2(project, cache=cache, recorder=v2_recorder)

        assert sorted(r2_v1.dispatched) == sorted(project.files)
        assert sorted(r2_v2.dispatched) == sorted(project.files)
        assert _normalize(r2_v1.findings) == _normalize(r2_v2.findings)


# ---------- multi-run sequence ----------

class TestMultiRunSequenceParity:
    def test_runs_track_same_dispatch_history(self, tmp_path: Path, cache: LocalFileBackend):
        project = _make_project(tmp_path, {
            "a.py": "v1",
            "b.py": "v1",
            "c.py": "v1",
        })
        v1_recorder = DispatchRecorder(project=project)
        v2_recorder = DispatchRecorder(project=project)

        # Run 1: cold.
        r1_v1 = run_v1(project, work_dir=tmp_path / "v1_run1", recorder=v1_recorder)
        r1_v2 = run_v2(project, cache=cache, recorder=v2_recorder)
        assert sorted(r1_v1.dispatched) == sorted(r1_v2.dispatched) == project.files

        # Run 2: no changes.
        v1_recorder.calls.clear()
        v2_recorder.calls.clear()
        r2_v1 = run_v1(
            project, work_dir=tmp_path / "v1_run2",
            prev_fingerprint=r1_v1.fingerprint,
            prev_jsonl=tmp_path / "v1_run1" / f"{project.dimension}_evidence.jsonl",
            recorder=v1_recorder,
        )
        r2_v2 = run_v2(project, cache=cache, recorder=v2_recorder)
        assert r2_v1.dispatched == r2_v2.dispatched == []

        # Run 3: change b.py.
        (project.src / "b.py").write_text("v2")
        v1_recorder.calls.clear()
        v2_recorder.calls.clear()
        r3_v1 = run_v1(
            project, work_dir=tmp_path / "v1_run3",
            prev_fingerprint=r2_v1.fingerprint,
            prev_jsonl=tmp_path / "v1_run2" / f"{project.dimension}_evidence.jsonl",
            recorder=v1_recorder,
        )
        r3_v2 = run_v2(project, cache=cache, recorder=v2_recorder)
        assert r3_v1.dispatched == r3_v2.dispatched == ["b.py"]
        assert _normalize(r3_v1.findings) == _normalize(r3_v2.findings)

        # Run 4: change c.py.
        (project.src / "c.py").write_text("v2")
        v1_recorder.calls.clear()
        v2_recorder.calls.clear()
        r4_v1 = run_v1(
            project, work_dir=tmp_path / "v1_run4",
            prev_fingerprint=r3_v1.fingerprint,
            prev_jsonl=tmp_path / "v1_run3" / f"{project.dimension}_evidence.jsonl",
            recorder=v1_recorder,
        )
        r4_v2 = run_v2(project, cache=cache, recorder=v2_recorder)
        assert r4_v1.dispatched == r4_v2.dispatched == ["c.py"]
        assert _normalize(r4_v1.findings) == _normalize(r4_v2.findings)


# ---------- carry-forward / cache equivalence ----------

class TestCarryForwardEquivalence:
    def test_v1_carry_forward_and_v2_cache_hit_yield_same_findings(self, tmp_path: Path, cache: LocalFileBackend):
        """Direct property: a finding written once and reused across runs
        appears byte-equal whether reused via JSONL carry-forward or
        cache hit."""
        project = _make_project(tmp_path, {"only.py": "content"})
        v1_recorder = DispatchRecorder(project=project)
        v2_recorder = DispatchRecorder(project=project)

        r1_v1 = run_v1(project, work_dir=tmp_path / "v1_run1", recorder=v1_recorder)
        r1_v2 = run_v2(project, cache=cache, recorder=v2_recorder)

        # Run 2: no changes anywhere; V1 carries forward, V2 hits.
        v1_recorder.calls.clear()
        v2_recorder.calls.clear()
        r2_v1 = run_v1(
            project, work_dir=tmp_path / "v1_run2",
            prev_fingerprint=r1_v1.fingerprint,
            prev_jsonl=tmp_path / "v1_run1" / f"{project.dimension}_evidence.jsonl",
            recorder=v1_recorder,
        )
        r2_v2 = run_v2(project, cache=cache, recorder=v2_recorder)

        # Carry-forward findings (V1) and cache-hit findings (V2) must be
        # identical to each other AND identical to run 1's output.
        assert _normalize(r2_v1.findings) == _normalize(r1_v1.findings)
        assert _normalize(r2_v2.findings) == _normalize(r1_v2.findings)
        assert _normalize(r2_v1.findings) == _normalize(r2_v2.findings)
