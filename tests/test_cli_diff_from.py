"""Parser and mutex tests for --diff-from."""
from __future__ import annotations

from quodeq.cli_parser import build_parser


def test_diff_from_accepts_ref() -> None:
    parser = build_parser()
    args = parser.parse_args(["evaluate", ".", "--diff-from", "origin/develop"])
    assert args.diff_from == "origin/develop"


def test_diff_from_defaults_to_none() -> None:
    parser = build_parser()
    args = parser.parse_args(["evaluate", "."])
    assert args.diff_from is None


def test_clean_scan_and_diff_from_mutually_exclusive(capsys) -> None:
    # The CLI must reject --clean-scan + --diff-from and exit non-zero
    # *before* running the pipeline. run_evaluate is the enforcement point.
    # Note: --incremental is now a deprecated no-op alias; the mutex is
    # between --clean-scan and --diff-from.
    from quodeq._cli_evaluation import run_evaluate

    parser = build_parser()
    args = parser.parse_args([
        "evaluate", ".", "--clean-scan", "--diff-from", "origin/develop",
    ])
    exit_code = run_evaluate(args)
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "--clean-scan" in err and "--diff-from" in err


def test_legacy_incremental_with_diff_from_does_not_error(capsys) -> None:
    """Deprecated --incremental no longer triggers the mutex when paired with --diff-from.

    Regression guard: the mutex was rewritten in Task 3 to check --clean-scan,
    not --incremental. The legacy flag is a no-op alias that emits a warning
    but should not block --diff-from runs.
    """
    from quodeq._cli_evaluation import run_evaluate

    parser = build_parser()
    args = parser.parse_args([
        "evaluate", ".", "--incremental", "--diff-from", "origin/develop", "--dry-run",
    ])
    exit_code = run_evaluate(args)

    # --dry-run bypasses prereq checks and returns 0 without launching a pipeline.
    assert exit_code == 0, (
        f"Expected exit code 0 with --dry-run; got {exit_code}. "
        "If this fails, check whether a mutex on legacy --incremental was re-introduced."
    )

    captured = capsys.readouterr()
    combined_output = (captured.out + captured.err).lower()

    # The mutex must NOT have fired. "mutually exclusive" appearing in output means
    # the legacy --incremental is incorrectly blocking --diff-from again.
    assert "mutually exclusive" not in combined_output, (
        "Output contains 'mutually exclusive' — the mutex on legacy --incremental "
        "has been re-introduced. Only --clean-scan should be mutex'd with --diff-from."
    )
    assert "--incremental" not in combined_output or "deprecated" in combined_output, (
        "If --incremental appears in error output it should only be in a deprecation warning, "
        "not a rejection message."
    )

    # The deprecation warning must be present so callers know to migrate.
    assert "deprecated" in combined_output, (
        "Expected a deprecation warning for --incremental but found none in stderr/stdout."
    )
