"""End-to-end smoke test for PR diff mode via the CLI.

Exercises the full ``uv run quodeq evaluate . --diff-from <ref> --dry-run``
flow against a real ephemeral git repo. The --dry-run flag skips AI calls
but still runs the whole pipeline: diff resolution, source file listing,
evidence writing, lifecycle. The assertions pin the behaviors that
define PR diff mode: evidence is produced, evaluation reports are not,
and the --incremental / --diff-from mutex is enforced at the process
boundary (not just at the argparse layer).
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True)


def _setup_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "t@t"], repo)
    _run(["git", "config", "user.name", "t"], repo)
    (repo / "base.py").write_text("def f(): return 1\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "base"], repo)
    _run(["git", "checkout", "-q", "-b", "feature"], repo)
    (repo / "pr_change.py").write_text("def g(): return 2\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "pr"], repo)
    return repo


def test_diff_mode_dry_run_produces_evidence_no_evaluation(tmp_path: Path) -> None:
    """Dry-run diff mode writes evidence JSONL and no scored evaluation JSON."""
    repo = _setup_repo(tmp_path)
    output = tmp_path / "out"
    result = subprocess.run(
        [
            "uv", "run", "quodeq", "evaluate", ".",
            "--diff-from", "main",
            "--dry-run",
            "--output", str(output),
        ],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"

    evidence_dirs = list(output.rglob("evidence"))
    assert evidence_dirs, (
        f"no evidence/ dir produced; out tree:\n"
        + "\n".join(str(p) for p in output.rglob("*"))
    )
    run_dir = evidence_dirs[0].parent

    # Diff mode writes per-dimension JSONL (empty in dry-run — the files exist
    # but have no rows because no AI ran). The directory-presence check is the
    # essential invariant: downstream `ci report --from-evidence` reads this.
    jsonl_files = list((run_dir / "evidence").glob("*_evidence.jsonl"))
    assert jsonl_files, "no evidence JSONL files produced"

    # Most importantly: no scored reports. The evaluation/ subdir may exist
    # (created by _setup_run_dirs) but must contain no <dim>.json reports.
    eval_dir = run_dir / "evaluation"
    if eval_dir.exists():
        eval_jsons = list(eval_dir.glob("*.json"))
        assert not eval_jsons, f"unexpected scored reports in diff mode: {eval_jsons}"


def test_diff_mode_incremental_mutex_is_enforced(tmp_path: Path) -> None:
    """--diff-from + --incremental must return 1 at the process boundary."""
    repo = _setup_repo(tmp_path)
    result = subprocess.run(
        [
            "uv", "run", "quodeq", "evaluate", ".",
            "--diff-from", "main", "--incremental",
            "--output", str(tmp_path / "out"),
        ],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "--incremental" in combined and "--diff-from" in combined
