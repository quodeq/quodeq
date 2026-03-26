# File Prioritization & Configurable Pool Budget — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analyze the most important files first (5-layer scoring) and let users control the analysis time limit.

**Architecture:** A new `priority.py` module computes per-file scores from path patterns, dimension keywords, import fan-in, git churn, and previous violations. The scored file list is fed to the existing FileQueue. Separately, `pool_budget` is split from `max_duration` and exposed to web UI. Both features are independent and can be tested separately.

**Tech Stack:** Python (backend), React (web UI), pytest (tests)

**Spec:** `docs/superpowers/specs/2026-03-22-file-prioritization-design.md`

**Dependency:** This branch should be based on `feat/token-optimization` (PR #107).

**Test command:** `uv run pytest tests/ -v` (from repo root, with `export PATH="$HOME/.local/bin:$PATH"`)

**Important:** Never add co-author lines to commits.

---

## Feature 1: File Prioritization

### Task 1: Config data file and config loader

**Files:**
- Create: `src/quodeq/data/config/file_priority.json`
- Create: `src/quodeq/analysis/subagents/priority.py`
- Test: `tests/engine/test_file_priority.py` (create)

- [ ] **Step 1: Write failing test for config loading**

Create `tests/engine/test_file_priority.py`:

```python
"""Tests for file priority scoring."""
from __future__ import annotations

from quodeq.analysis.subagents.priority import load_priority_config


class TestLoadPriorityConfig:
    def test_loads_default_config(self):
        config = load_priority_config()
        assert "path_boost" in config
        assert "dimension_keywords" in config
        assert "import_patterns" in config
        assert config["default_path_score"] == 2

    def test_cached_on_second_call(self):
        c1 = load_priority_config()
        c2 = load_priority_config()
        assert c1 is c2  # same object, cached
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/engine/test_file_priority.py::TestLoadPriorityConfig -v`
Expected: ImportError — module doesn't exist.

- [ ] **Step 3: Create `file_priority.json`**

Create `src/quodeq/data/config/file_priority.json` with the full config from the spec (path_boost, entry_points, category_keywords, dimension_keywords, import_patterns, all thresholds).

- [ ] **Step 4: Create `priority.py` with config loader**

Create `src/quodeq/analysis/subagents/priority.py`:

```python
"""File priority scoring — ranks source files by analysis importance."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from quodeq.config.paths import default_paths


@lru_cache(maxsize=1)
def load_priority_config() -> dict:
    """Load file priority config. Cached after first call."""
    config_path = default_paths().root / "config" / "file_priority.json"
    return json.loads(config_path.read_text())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_file_priority.py::TestLoadPriorityConfig -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/data/config/file_priority.json src/quodeq/analysis/subagents/priority.py tests/engine/test_file_priority.py
git commit -m "feat: file priority config and loader"
```

---

### Task 2: Layer 1 — Base score (path patterns, entry points, category)

**Files:**
- Modify: `src/quodeq/analysis/subagents/priority.py`
- Test: `tests/engine/test_file_priority.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/engine/test_file_priority.py`:

```python
from quodeq.analysis.subagents.priority import compute_base_score


class TestComputeBaseScore:
    def test_src_directory_high_score(self):
        score = compute_base_score("src/quodeq/runner.py")
        assert score >= 5  # src/ path boost

    def test_test_directory_low_score(self):
        score = compute_base_score("tests/test_runner.py")
        assert score <= 2  # tests/ path boost = 1

    def test_unknown_path_gets_default(self):
        score = compute_base_score("random/file.py")
        assert score == 2  # default_path_score

    def test_entry_point_boost(self):
        score_entry = compute_base_score("src/main.py")
        score_normal = compute_base_score("src/utils.py")
        assert score_entry > score_normal  # entry point gets +3

    def test_category_boost_backend(self):
        score = compute_base_score("src/controller.py", category="backend")
        score_plain = compute_base_score("src/utils.py", category="backend")
        assert score > score_plain  # "controller" keyword matches backend

    def test_category_boost_mobile(self):
        score = compute_base_score("src/LoginActivity.java", category="mobile")
        score_plain = compute_base_score("src/Utils.java", category="mobile")
        assert score > score_plain

    def test_no_category(self):
        # Should not crash when category is None
        score = compute_base_score("src/file.py", category=None)
        assert score >= 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_file_priority.py::TestComputeBaseScore -v`
Expected: ImportError.

- [ ] **Step 3: Implement `compute_base_score`**

Add to `src/quodeq/analysis/subagents/priority.py`:

```python
import fnmatch
import os


def compute_base_score(filepath: str, category: str | None = None) -> int:
    """Layer 1: base score from path patterns, entry points, and category."""
    config = load_priority_config()
    score = config["default_path_score"]

    # Path boost: match first directory segment
    filepath_lower = filepath.lower().replace("\\", "/")
    for prefix, boost in config["path_boost"].items():
        if filepath_lower.startswith(prefix) or f"/{prefix}" in filepath_lower:
            score = boost
            break

    # Entry point boost
    basename = os.path.basename(filepath_lower)
    for pattern in config["entry_points"]:
        if fnmatch.fnmatch(basename, pattern.lower()):
            score += config["entry_point_boost"]
            break

    # Category keyword boost
    if category and category in config.get("category_keywords", {}):
        keywords = config["category_keywords"][category]
        for kw in keywords:
            if kw in filepath_lower:
                score += config["category_keyword_boost"]
                break

    return score
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_file_priority.py::TestComputeBaseScore -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/analysis/subagents/priority.py tests/engine/test_file_priority.py
git commit -m "feat: Layer 1 base score — path patterns, entry points, category"
```

---

### Task 3: Layer 2 — Dimension boost (keywords + file size for maintainability)

**Files:**
- Modify: `src/quodeq/analysis/subagents/priority.py`
- Test: `tests/engine/test_file_priority.py`

- [ ] **Step 1: Write failing tests**

```python
from quodeq.analysis.subagents.priority import compute_dimension_boost


class TestComputeDimensionBoost:
    def test_security_keyword_match(self):
        score = compute_dimension_boost("src/auth_handler.py", "security")
        assert score == 5

    def test_security_no_match(self):
        score = compute_dimension_boost("src/utils.py", "security")
        assert score == 0

    def test_reliability_keyword_match(self):
        score = compute_dimension_boost("src/error_handler.py", "reliability")
        assert score == 5

    def test_maintainability_uses_file_size(self, tmp_path):
        # Create a 10KB file
        big = tmp_path / "big.py"
        big.write_text("x" * 10000)
        score = compute_dimension_boost(str(big), "maintainability", file_size=10000)
        assert score == 5  # 10000 / 2000 = 5

    def test_maintainability_small_file(self):
        score = compute_dimension_boost("src/tiny.py", "maintainability", file_size=500)
        assert score == 0  # 500 / 2000 = 0.25 → 0

    def test_consolidated_max_across_dimensions(self):
        # auth_handler matches security (+5) but not maintainability
        score = compute_dimension_boost("src/auth_handler.py", ["security", "maintainability"])
        assert score == 5  # max(5, 0)

    def test_unknown_dimension(self):
        score = compute_dimension_boost("src/file.py", "unknown_dim")
        assert score == 0
```

- [ ] **Step 2: Implement `compute_dimension_boost`**

```python
def compute_dimension_boost(
    filepath: str,
    dimension: str | list[str],
    file_size: int = 0,
) -> int:
    """Layer 2: dimension-specific keyword boost or file-size boost."""
    config = load_priority_config()
    dims = dimension if isinstance(dimension, list) else [dimension]
    filepath_lower = filepath.lower().replace("\\", "/")

    best = 0
    for dim in dims:
        keywords = config.get("dimension_keywords", {}).get(dim, [])
        if not keywords and dim == "maintainability":
            # Maintainability uses file size instead of keywords
            divisor = config.get("maintainability_size_divisor", 2000)
            score = min(5, int(file_size / divisor))
        else:
            score = 0
            for kw in keywords:
                if kw in filepath_lower:
                    score = config.get("dimension_keyword_boost", 5)
                    break
        best = max(best, score)
    return best
```

- [ ] **Step 3: Run tests, commit**

```bash
git add src/quodeq/analysis/subagents/priority.py tests/engine/test_file_priority.py
git commit -m "feat: Layer 2 dimension boost — keywords + maintainability file size"
```

---

### Task 4: Layer 3 — Import fan-in

**Files:**
- Modify: `src/quodeq/analysis/subagents/priority.py`
- Test: `tests/engine/test_file_priority.py`

- [ ] **Step 1: Write failing tests**

```python
from quodeq.analysis.subagents.priority import compute_fan_in


class TestComputeFanIn:
    def test_counts_python_imports(self, tmp_path):
        # Create source files with imports
        (tmp_path / "main.py").write_text("from auth import login\nimport utils\n")
        (tmp_path / "handler.py").write_text("from auth import verify\n")
        (tmp_path / "auth.py").write_text("# no imports\n")
        (tmp_path / "utils.py").write_text("# no imports\n")

        files = ["main.py", "handler.py", "auth.py", "utils.py"]
        fan_in = compute_fan_in(files, tmp_path, "python")
        # "auth" imported by main.py and handler.py → fan_in = 2
        assert fan_in.get("auth.py", 0) >= 2
        # "utils" imported by main.py → fan_in = 1
        assert fan_in.get("utils.py", 0) >= 1

    def test_javascript_imports(self, tmp_path):
        (tmp_path / "app.js").write_text("import { foo } from './auth'\nconst bar = require('./utils')\n")
        (tmp_path / "auth.js").write_text("")
        (tmp_path / "utils.js").write_text("")

        files = ["app.js", "auth.js", "utils.js"]
        fan_in = compute_fan_in(files, tmp_path, "javascript")
        assert fan_in.get("auth.js", 0) >= 1
        assert fan_in.get("utils.js", 0) >= 1

    def test_no_imports_returns_empty(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        fan_in = compute_fan_in(["a.py"], tmp_path, "python")
        assert fan_in == {} or all(v == 0 for v in fan_in.values())

    def test_unknown_language_returns_empty(self, tmp_path):
        fan_in = compute_fan_in(["a.xyz"], tmp_path, "cobol")
        assert fan_in == {}
```

- [ ] **Step 2: Implement `compute_fan_in`**

```python
import re


def compute_fan_in(
    files: list[str], src: Path, language: str,
) -> dict[str, int]:
    """Layer 3: count how many files import each file."""
    config = load_priority_config()
    # Normalize language name to match config keys (e.g., "Python" → "python",
    # "TypeScript" → "javascript" since they share import syntax)
    lang_key = language.lower()
    _LANG_ALIASES = {"typescript": "javascript", "jsx": "javascript", "tsx": "javascript", "kotlin": "java"}
    lang_key = _LANG_ALIASES.get(lang_key, lang_key)
    patterns = config.get("import_patterns", {}).get(lang_key)
    if not patterns:
        return {}

    # Build filename lookup: stem → relative path
    stem_to_file: dict[str, str] = {}
    for f in files:
        stem = Path(f).stem
        stem_to_file.setdefault(stem, f)

    compiled = [re.compile(p) for p in patterns]
    counts: dict[str, int] = {}

    for f in files:
        full_path = src / f
        if not full_path.exists():
            continue
        try:
            content = full_path.read_text(errors="ignore")
        except OSError:
            continue
        for line in content.splitlines():
            for pattern in compiled:
                m = pattern.search(line)
                if m:
                    imported = m.group(1)
                    # Normalize: take last segment of dotted path
                    module_name = imported.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
                    if module_name in stem_to_file:
                        target = stem_to_file[module_name]
                        if target != f:  # don't count self-imports
                            counts[target] = counts.get(target, 0) + 1
                    break  # one match per line is enough

    return counts
```

- [ ] **Step 3: Run tests, commit**

```bash
git add src/quodeq/analysis/subagents/priority.py tests/engine/test_file_priority.py
git commit -m "feat: Layer 3 import fan-in scoring"
```

---

### Task 5: Layer 4 — Git history signals

**Files:**
- Modify: `src/quodeq/analysis/subagents/priority.py`
- Test: `tests/engine/test_file_priority.py`

- [ ] **Step 1: Write failing tests**

```python
from unittest.mock import patch
from quodeq.analysis.subagents.priority import compute_git_scores


class TestComputeGitScores:
    def test_parses_git_log(self, tmp_path):
        mock_output = "abc123\n2026-03-20\nfile1.py\nfile2.py\n\ndef456\n2026-03-10\nfile1.py\n\n"
        with patch("quodeq.analysis.subagents.priority._run_git_log", return_value=mock_output):
            scores = compute_git_scores(["file1.py", "file2.py"], tmp_path)
        # file1.py: 2 commits → churn score
        assert scores.get("file1.py", 0) > scores.get("file2.py", 0)

    def test_git_not_available(self, tmp_path):
        with patch("quodeq.analysis.subagents.priority._run_git_log", return_value=None):
            scores = compute_git_scores(["file1.py"], tmp_path)
        assert scores == {}

    def test_recent_file_gets_recency_boost(self, tmp_path):
        # File changed today vs 2 months ago
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        old = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        mock_output = f"abc\n{today}\nrecent.py\n\ndef\n{old}\nold.py\n\n"
        with patch("quodeq.analysis.subagents.priority._run_git_log", return_value=mock_output):
            scores = compute_git_scores(["recent.py", "old.py"], tmp_path)
        # Both have 1 commit, but recent.py gets recency multiplier
        assert scores.get("recent.py", 0) >= scores.get("old.py", 0)
```

- [ ] **Step 2: Implement `compute_git_scores` and `_run_git_log`**

```python
import subprocess
from datetime import datetime, timedelta


def _run_git_log(src: Path, months: int = 3) -> str | None:
    """Run git log and return raw output, or None if git unavailable."""
    if not (src / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "log", f"--since={months} months ago", "--name-only", "--format=%H%n%ai"],
            cwd=str(src), capture_output=True, text=True, timeout=10,
        )
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def compute_git_scores(files: list[str], src: Path) -> dict[str, float]:
    """Layer 4: git churn and recency scoring."""
    config = load_priority_config()
    raw = _run_git_log(src, config.get("git_lookback_months", 3))
    if not raw:
        return {}

    file_set = set(files)
    churn: dict[str, int] = {}
    last_date: dict[str, str] = {}

    # Parse git log output: alternating commit info and file lists
    current_date = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Date lines contain timezone offset like "+0100"
        if len(line) >= 10 and line[4] == "-" and line[7] == "-":
            current_date = line[:10]  # YYYY-MM-DD
            continue
        # 40-char hex = commit hash, skip
        if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
            continue
        # File path
        if line in file_set:
            churn[line] = churn.get(line, 0) + 1
            if line not in last_date or current_date > last_date[line]:
                last_date[line] = current_date

    divisor = config.get("git_churn_divisor", 4)
    max_score = config.get("git_churn_max", 5)
    recency_days = config.get("git_recency_days", 14)
    recency_mult = config.get("git_recency_multiplier", 1.5)
    cutoff = (datetime.now() - timedelta(days=recency_days)).strftime("%Y-%m-%d")

    scores: dict[str, float] = {}
    for f in files:
        c = churn.get(f, 0)
        if c == 0:
            continue
        score = min(max_score, c / divisor)
        # Recency boost
        if last_date.get(f, "") >= cutoff:
            score = min(max_score, score * recency_mult)
        scores[f] = score

    return scores
```

- [ ] **Step 3: Run tests, commit**

```bash
git add src/quodeq/analysis/subagents/priority.py tests/engine/test_file_priority.py
git commit -m "feat: Layer 4 git history signals — churn and recency"
```

---

### Task 6: Layer 5 — Previous violations boost

**Files:**
- Modify: `src/quodeq/analysis/subagents/priority.py`
- Test: `tests/engine/test_file_priority.py`

- [ ] **Step 1: Write failing tests**

```python
import json
from quodeq.analysis.subagents.priority import compute_previous_violations


class TestComputePreviousViolations:
    def test_counts_violations_per_file(self, tmp_path):
        """Mock load_previous_findings_for_dimension to return test findings."""
        findings = [
            {"p": "Confidentiality", "d": "security", "t": "violation", "file": "auth.py", "line": 1},
            {"p": "Confidentiality", "d": "security", "t": "violation", "file": "auth.py", "line": 5},
            {"p": "Integrity", "d": "security", "t": "violation", "file": "routes.py", "line": 10},
            {"p": "Integrity", "d": "security", "t": "compliance", "file": "utils.py", "line": 1},
        ]
        with patch("quodeq.analysis.subagents.priority.load_previous_findings_for_dimension", return_value=findings):
            counts = compute_previous_violations(None, tmp_path, "security")
        assert counts.get("auth.py", 0) == 2
        assert counts.get("routes.py", 0) == 1
        assert counts.get("utils.py", 0) == 0  # compliance, not violation

    def test_no_previous_run(self, tmp_path):
        with patch("quodeq.analysis.subagents.priority.load_previous_findings_for_dimension", return_value=[]):
            counts = compute_previous_violations(None, tmp_path, "security")
        assert counts == {}

    def test_consolidated_merges_dimensions(self, tmp_path):
        def mock_load(config, dim, evidence_dir):
            if dim == "security":
                return [{"t": "violation", "file": "auth.py", "line": 1}]
            elif dim == "maintainability":
                return [{"t": "violation", "file": "big.py", "line": 1}]
            return []
        with patch("quodeq.analysis.subagents.priority.load_previous_findings_for_dimension", side_effect=mock_load):
            counts = compute_previous_violations(None, tmp_path, ["security", "maintainability"])
        assert counts.get("auth.py", 0) >= 1
        assert counts.get("big.py", 0) >= 1
```

- [ ] **Step 2: Implement `compute_previous_violations`**

```python
def compute_previous_violations(
    config: Any, evidence_dir: Path, dimension: str | list[str],
) -> dict[str, int]:
    """Layer 5: count violations per file from previous evaluation.

    Reuses load_previous_findings_for_dimension from verify.py which
    resolves the correct previous run's evidence directory.
    """
    from quodeq.analysis.subagents.verify import load_previous_findings_for_dimension

    dims = dimension if isinstance(dimension, list) else [dimension]
    counts: dict[str, int] = {}

    for dim in dims:
        try:
            findings = load_previous_findings_for_dimension(config, dim, evidence_dir)
        except Exception:
            continue
        for finding in findings:
            if finding.get("t") == "violation" and finding.get("file"):
                f = finding["file"]
                counts[f] = counts.get(f, 0) + 1

    return counts
```

- [ ] **Step 3: Run tests, commit**

```bash
git add src/quodeq/analysis/subagents/priority.py tests/engine/test_file_priority.py
git commit -m "feat: Layer 5 previous violations boost"
```

---

### Task 7: `prioritize_files` — combine all layers

**Files:**
- Modify: `src/quodeq/analysis/subagents/priority.py`
- Test: `tests/engine/test_file_priority.py`

- [ ] **Step 1: Write failing tests**

```python
from quodeq.analysis.subagents.priority import prioritize_files


class TestPrioritizeFiles:
    def test_returns_sorted_by_score_descending(self, tmp_path):
        # Create files: src/important.py and tests/boring.py
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "important.py").write_text("x" * 100)
        (tmp_path / "tests" / "boring.py").write_text("x" * 10)

        files = ["tests/boring.py", "src/important.py"]
        result = prioritize_files(files, tmp_path, "security", category=None)
        assert result[0] == "src/important.py"  # higher base score

    def test_all_files_preserved(self, tmp_path):
        files = [f"file{i}.py" for i in range(20)]
        for f in files:
            (tmp_path / f).write_text("")
        result = prioritize_files(files, tmp_path, "security", category=None)
        assert set(result) == set(files)
        assert len(result) == 20

    def test_dimension_affects_order(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text("x" * 100)
        (tmp_path / "src" / "utils.py").write_text("x" * 100)

        files = ["src/utils.py", "src/auth.py"]
        security_order = prioritize_files(files, tmp_path, "security")
        # auth.py should be first for security (matches "auth" keyword)
        assert security_order[0] == "src/auth.py"

    def test_consolidated_uses_max_dimension_boost(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text("x")
        (tmp_path / "src" / "error_handler.py").write_text("x")

        files = ["src/auth.py", "src/error_handler.py"]
        result = prioritize_files(files, tmp_path, ["security", "reliability"])
        # Both should score high — auth matches security, error matches reliability
        assert len(result) == 2
```

- [ ] **Step 2: Implement `prioritize_files`**

```python
def prioritize_files(
    files: list[str],
    src: Path,
    dimension: str | list[str],
    category: str | None = None,
    language: str | None = None,
    evidence_dir: Path | None = None,
    config: Any = None,
) -> list[str]:
    """Score and sort files by analysis priority (highest first)."""
    config = load_priority_config()
    max_prev_violations = config.get("previous_violations_max", 5)
    fan_in_divisor = config.get("fan_in_divisor", 3)
    fan_in_max = config.get("fan_in_max", 5)

    # Batch computations (one pass each)
    fan_in = compute_fan_in(files, src, language or "") if language else {}
    git_scores = compute_git_scores(files, src)
    prev_violations = compute_previous_violations(config, evidence_dir, dimension) if evidence_dir and config else {}

    scored: list[tuple[float, str]] = []
    for f in files:
        # Layer 1: base
        base = compute_base_score(f, category)

        # Layer 2: dimension
        file_size = 0
        try:
            file_size = (src / f).stat().st_size
        except OSError:
            pass
        dim_boost = compute_dimension_boost(f, dimension, file_size=file_size)

        # Layer 3: fan-in
        fi_raw = fan_in.get(f, 0)
        fi_score = min(fan_in_max, fi_raw / fan_in_divisor) if fi_raw > 0 else 0

        # Layer 4: git
        git_score = git_scores.get(f, 0)

        # Layer 5: previous violations
        pv_count = prev_violations.get(f, 0)
        pv_score = min(max_prev_violations, pv_count)

        total = base + dim_boost + fi_score + git_score + pv_score
        scored.append((total, f))

    # Sort descending by score, alphabetically as tiebreaker
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [f for _, f in scored]
```

- [ ] **Step 3: Run tests, commit**

```bash
git add src/quodeq/analysis/subagents/priority.py tests/engine/test_file_priority.py
git commit -m "feat: prioritize_files — combine all 5 scoring layers"
```

---

### Task 8: Wire prioritization into subagent runner

**Files:**
- Modify: `src/quodeq/analysis/subagents/runner.py`
- Test: `tests/engine/test_file_priority.py` (integration test)

- [ ] **Step 1: Write integration test**

```python
class TestPrioritizationIntegration:
    def test_list_source_files_returns_prioritized(self, tmp_path):
        """Verify _list_source_files returns files in priority order."""
        from quodeq.analysis.subagents.runner import _list_source_files
        from quodeq.analysis.runner import RunConfig, AnalysisOptions
        from quodeq.analysis.manifest import AnalysisTarget, SourceManifest

        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "auth.py").write_text("x" * 100)
        (tmp_path / "tests" / "test_stuff.py").write_text("x" * 100)

        target = AnalysisTarget(
            name="python", language="python", category="backend",
            source_files=["tests/test_stuff.py", "src/auth.py"],
            total_files=2,
        )
        config = RunConfig(
            src=tmp_path, language="python",
            options=AnalysisOptions(),
            target=target,
            manifest=SourceManifest(targets=[target], total_files=2),
        )
        files, _ = _list_source_files(config, "security")
        # src/auth.py should come before tests/test_stuff.py
        assert files.index("src/auth.py") < files.index("tests/test_stuff.py")
```

- [ ] **Step 2: Modify `_list_source_files` in runner.py**

In `src/quodeq/analysis/subagents/runner.py`, modify `_list_source_files` to call `prioritize_files` before returning:

```python
from quodeq.analysis.subagents.priority import prioritize_files

def _list_source_files(config: RunConfig, dim_id: str) -> tuple[list[str], set[str]]:
    # ... existing logic to get files and extensions ...

    # Prioritize before returning
    category = None
    if config.target and config.target.category:
        category = config.target.category
    elif config.manifest:
        category = config.manifest.category

    evidence_dir = config.work_dir or config.src
    files = prioritize_files(
        files, config.src, dim_id,
        category=category,
        language=config.language,
        evidence_dir=evidence_dir,
    )
    return files, extensions
```

- [ ] **Step 3: Run tests, run full suite**

Run: `uv run pytest tests/ -v`

- [ ] **Step 4: Commit**

```bash
git add src/quodeq/analysis/subagents/runner.py tests/engine/test_file_priority.py
git commit -m "feat: wire file prioritization into subagent runner"
```

---

## Feature 2: Configurable Pool Budget

### Task 9: Split pool_budget from max_duration in AnalysisConfig

**Files:**
- Modify: `src/quodeq/analysis/subprocess.py`
- Modify: `src/quodeq/analysis/subagents/pool.py`
- Test: `tests/engine/test_subagent_pool.py`

- [ ] **Step 1: Write failing test**

Add to `tests/engine/test_subagent_pool.py`:

```python
class TestPoolBudget:
    def test_pool_uses_pool_budget_not_max_duration(self, tmp_path):
        """Pool time limit should use pool_budget, not max_duration."""
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"f{i}.py" for i in range(5)])

        # pool_budget=60, max_duration=1800 — pool should respect 60
        ac = AnalysisConfig(pool_budget=60, max_duration=1800, max_files_per_agent=30)
        pool = SubagentPool(
            n_agents=1,
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            prompt="test",
            dimension="security",
            config=ac,
        )
        # Verify the pool reads pool_budget
        assert pool._base_config.pool_budget == 60
        assert pool._base_config.max_duration == 1800
```

- [ ] **Step 2: Add `pool_budget` to `AnalysisConfig`**

In `src/quodeq/analysis/subprocess.py`, add to the frozen dataclass:

```python
pool_budget: int = 600
```

- [ ] **Step 3: Update `SubagentPool.run()` to use `pool_budget`**

In `src/quodeq/analysis/subagents/pool.py`, change `run()`:

```python
max_duration = self._base_config.pool_budget or self._base_config.max_duration or _DEFAULT_POOL_BUDGET
```

And in `_build_agent_config`, keep using `max_duration` for per-agent timeout. Explicitly update line 102 to remove the `_DEFAULT_POOL_BUDGET` fallback:

```python
# Before (conflated):
agent_max_duration = self._base_config.max_duration or _DEFAULT_POOL_BUDGET
# After (split):
agent_max_duration = self._base_config.max_duration or 1800  # per-agent timeout, not pool budget
```

- [ ] **Step 4: Run tests, commit**

```bash
git add src/quodeq/analysis/subprocess.py src/quodeq/analysis/subagents/pool.py tests/engine/test_subagent_pool.py
git commit -m "feat: split pool_budget from max_duration in AnalysisConfig"
```

---

### Task 10: CLI flag and env var for pool budget

**Files:**
- Modify: `src/quodeq/cli_parser.py`
- Modify: `src/quodeq/cli.py`
- Modify: `src/quodeq/analysis/runner.py`

- [ ] **Step 1: Add `--pool-budget` to CLI parser**

In `src/quodeq/cli_parser.py`:

```python
parser.add_argument(
    "--pool-budget", type=int, default=None,
    help="Total time budget for agent pool in seconds (default: 600)",
)
```

- [ ] **Step 2: Add `pool_budget` to `AnalysisOptions`**

In `src/quodeq/analysis/runner.py`:

```python
pool_budget: int | None = None
```

- [ ] **Step 3: Wire in `cli.py`**

In `src/quodeq/cli.py`, where `AnalysisOptions` is constructed, add:

```python
pool_budget=args.pool_budget or _env_int("QUODEQ_POOL_BUDGET", None),
```

(Check how `_env_int` is used for `max_turns`/`max_duration` and follow the same pattern.)

- [ ] **Step 4: Wire `pool_budget` into `AnalysisConfig` construction**

In `src/quodeq/analysis/runner.py`, where `AnalysisConfig` is built (in `_run_dimension_analysis` and in `subagents/runner.py` `_launch_pool`), pass `pool_budget` when set:

```python
if config.options.pool_budget is not None:
    ac_kwargs["pool_budget"] = config.options.pool_budget
```

- [ ] **Step 5: Run full suite, commit**

```bash
git add src/quodeq/cli_parser.py src/quodeq/cli.py src/quodeq/analysis/runner.py
git commit -m "feat: --pool-budget CLI flag and QUODEQ_POOL_BUDGET env var"
```

---

### Task 11: Expose pool budget in web API and UI

**Files:**
- Modify: `src/quodeq/services/base.py`
- Modify: `src/quodeq/services/evaluation_mixin.py`
- Modify: `src/quodeq/api/routes.py`
- Modify: `src/quodeq/ui/src/features/settings/components/SettingsPage.jsx`
- Modify: `src/quodeq/ui/src/features/evaluation/hooks/useEvaluation.js`

- [ ] **Step 1: Add `pool_budget` to `EvaluationOptions`**

In `src/quodeq/services/base.py`:

```python
pool_budget: int = 600
```

- [ ] **Step 2: Pass via env var in `_build_eval_env`**

In `src/quodeq/services/evaluation_mixin.py`, in `_build_eval_env`:

```python
if options.pool_budget != 600:
    env["QUODEQ_POOL_BUDGET"] = str(options.pool_budget)
```

- [ ] **Step 3: Accept `poolBudget` in API route**

In `src/quodeq/api/routes.py`:

```python
pool_budget_raw = payload.get("poolBudget", 600)
pool_budget = max(60, min(3600, int(pool_budget_raw)))
```

Pass to `EvaluationOptions(pool_budget=pool_budget, ...)`.

- [ ] **Step 4: Add UI control**

In `SettingsPage.jsx`: add "Analysis time limit" number input (minutes, range 1-60, default 10). Store in localStorage as `cc-pool-budget` in seconds. Follow same pattern as `cc-max-subagents`.

In `useEvaluation.js`: read `cc-pool-budget` from localStorage and include as `poolBudget` in the API payload when non-default.

- [ ] **Step 5: Run backend tests, commit**

```bash
git add src/quodeq/services/base.py src/quodeq/services/evaluation_mixin.py src/quodeq/api/routes.py src/quodeq/ui/
git commit -m "feat: expose pool budget setting in web API and UI"
```

---

### Task 12: Full integration test

**Files:**
- Create: `tests/engine/test_prioritization_integration.py`

- [ ] **Step 1: Write end-to-end test**

Test that for a mock project with files in src/ and tests/, the FileQueue receives files sorted with src/ files first when evaluating security.

Test that pool_budget flows from AnalysisOptions through to SubagentPool.

- [ ] **Step 2: Run full suite**

Run: `uv run pytest tests/ -v`

- [ ] **Step 3: Commit**

```bash
git add tests/engine/test_prioritization_integration.py
git commit -m "test: end-to-end integration tests for file prioritization and pool budget"
```

---

## Summary

| Task | Feature | Description | Key files |
|------|---------|-------------|-----------|
| 1 | Prioritization | Config file + loader | `file_priority.json`, `priority.py` |
| 2 | Prioritization | Layer 1: base score | `priority.py` |
| 3 | Prioritization | Layer 2: dimension boost | `priority.py` |
| 4 | Prioritization | Layer 3: import fan-in | `priority.py` |
| 5 | Prioritization | Layer 4: git history | `priority.py` |
| 6 | Prioritization | Layer 5: previous violations | `priority.py` |
| 7 | Prioritization | Combine all layers | `priority.py` |
| 8 | Prioritization | Wire into runner | `runner.py` |
| 9 | Pool Budget | Split pool_budget from max_duration | `subprocess.py`, `pool.py` |
| 10 | Pool Budget | CLI flag + env var | `cli_parser.py`, `cli.py` |
| 11 | Pool Budget | Web API + UI | `base.py`, `routes.py`, UI |
| 12 | Both | Integration test | test file |
