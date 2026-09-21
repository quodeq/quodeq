"""Unit tests and gate for tools/check_dead_code.py: the vulture ratchet."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_dead_code

TOOLS = Path(__file__).resolve().parents[2] / "tools"

SAMPLE = """\
src/quodeq/_cli_env.py:91: unused variable 'ENV_MAX_TURNS' (60% confidence)
src/quodeq/api/app.py:12: unused function 'make_thing' (60% confidence)
src/quodeq/api/app.py:40: unused method 'teardown' (60% confidence)
src/quodeq/core/x.py:3: unused class 'Legacy' (60% confidence)
src/quodeq/core/x.py:9: unused property 'stale' (60% confidence)
src/quodeq/core/x.py:11: unused class attribute 'CACHE' (60% confidence)
src/quodeq/shared/run_log.py:73: unused variable 'tb' (100% confidence)
"""


def test_gate_passes_on_current_tree():
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "check_dead_code.py")],
        capture_output=True, text=True, check=False, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_parser_reads_every_report_kind():
    hits = check_dead_code.parse_report(SAMPLE)
    assert [(h.kind, h.name) for h in hits] == [
        ("variable", "ENV_MAX_TURNS"),
        ("function", "make_thing"),
        ("method", "teardown"),
        ("class", "Legacy"),
        ("property", "stale"),
        ("class attribute", "CACHE"),
        ("variable", "tb"),
    ]


def test_parser_keeps_path_line_and_confidence():
    first, *_, last = check_dead_code.parse_report(SAMPLE)
    assert (first.path, first.line, first.confidence) == ("src/quodeq/_cli_env.py", 91, 60)
    assert (last.path, last.line, last.confidence) == ("src/quodeq/shared/run_log.py", 73, 100)


def test_violation_key_is_relpath_line_and_name():
    (hit,) = check_dead_code.parse_report(
        "src/quodeq/api/app.py:12: unused function 'make_thing' (60% confidence)\n"
    )
    assert check_dead_code.violation_key(hit) == "src/quodeq/api/app.py:12:make_thing"
    assert check_dead_code.describe(hit) == (
        "src/quodeq/api/app.py:12:make_thing: unused function (60% confidence)"
    )


def test_two_reports_on_one_line_are_two_keys():
    """Unlike the env-read ratchet, the name is part of the key, so a line
    defining two unused names keeps one entry per name."""
    hits = check_dead_code.parse_report(
        "src/quodeq/core/x.py:5: unused variable 'A' (60% confidence)\n"
        "src/quodeq/core/x.py:5: unused variable 'B' (60% confidence)\n"
    )
    assert [h.key for h in hits] == ["src/quodeq/core/x.py:5:A", "src/quodeq/core/x.py:5:B"]


def test_windows_paths_are_normalised():
    (hit,) = check_dead_code.parse_report(
        "src\\quodeq\\api\\app.py:12: unused function 'f' (60% confidence)\n"
    )
    assert hit.key == "src/quodeq/api/app.py:12:f"


def test_blank_lines_are_ignored_and_unparsed_lines_warn(capsys):
    hits = check_dead_code.parse_report(
        "\n"
        "src/quodeq/core/x.py:5: unreachable code after 'return' (100% confidence)\n"
        "src/quodeq/core/x.py:9: unused function 'f' (60% confidence)\n"
    )
    assert [h.name for h in hits] == ["f"]
    assert "unreachable code" in capsys.readouterr().err


def test_scan_uses_min_confidence_60():
    """80 reports only unused locals and unreachable code, which ruff's F841
    already covers; 60 is what surfaces unreferenced functions and methods."""
    assert check_dead_code.MIN_CONFIDENCE == 60


def test_whitelist_is_scanned_alongside_src():
    """The whitelist only counts as "used" when vulture reads it in the same
    run as the tree it exonerates."""
    assert check_dead_code.SCAN_PATHS == ("src/quodeq", "tools/vulture_whitelist.py")
    assert (TOOLS / "vulture_whitelist.py").exists()


def test_update_baseline_with_no_reports_writes_header_only(tmp_path, monkeypatch):
    monkeypatch.setattr(check_dead_code, "run_vulture", lambda *a, **k: "")
    baseline = tmp_path / "dead_code_baseline.txt"

    assert check_dead_code.write_baseline(baseline) == 0
    lines = baseline.read_text(encoding="utf-8").splitlines()
    assert lines and all(line.startswith("#") for line in lines)
    assert check_dead_code.load_baseline(baseline) == set()


def test_update_baseline_writes_sorted_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(check_dead_code, "run_vulture", lambda *a, **k: SAMPLE)
    baseline = tmp_path / "dead_code_baseline.txt"

    assert check_dead_code.write_baseline(baseline) == 7
    keys = sorted(check_dead_code.load_baseline(baseline))
    assert keys[0] == "src/quodeq/_cli_env.py:91:ENV_MAX_TURNS"
    assert "src/quodeq/core/x.py:11:CACHE" in keys


def test_run_vulture_raises_on_an_unexpected_exit_code(monkeypatch):
    monkeypatch.setattr(check_dead_code.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=a, returncode=1, stdout="", stderr="boom",
    ))
    try:
        check_dead_code.run_vulture()
    except RuntimeError as e:
        assert "boom" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_no_new_dead_code_violations():
    baseline = check_dead_code.load_baseline()
    new = sorted(set(check_dead_code.collect_violations()) - baseline)
    assert new == [], (
        "New dead code in src/quodeq. Delete the definition once a grep over "
        "src, tests, tools, CI and docs shows nothing references it; if it is "
        "reached dynamically, add it to tools/vulture_whitelist.py with a "
        "reason:\n" + "\n".join(new)
    )


def test_baseline_has_no_stale_entries():
    current = set(check_dead_code.collect_violations())
    stale = sorted(check_dead_code.load_baseline() - current)
    assert stale == [], (
        "Baseline lists reports that no longer exist; regenerate with "
        "`python tools/check_dead_code.py --update-baseline`:\n" + "\n".join(stale)
    )


# Revise DOWNWARD as PR 6 Tasks 2-3 and later burn-downs delete the dead
# definitions; the target is 0. NEVER raise without a justification reviewed
# in the PR that raises it.
BASELINE_CEILING = 303


def test_baseline_only_shrinks():
    count = len(check_dead_code.load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). "
        "Delete the dead definition instead of grandfathering it."
    )
