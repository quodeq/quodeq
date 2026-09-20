"""Unit tests and gate for tools/check_clones.py: copy-paste duplication."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import _clones_rules
import check_clones

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _payload(*pairs):
    """Build a jscpd-shaped report from (nameA, startA, endA, nameB, startB, endB)."""
    return {
        "duplicates": [
            {
                "format": "python",
                "lines": end_a - start_a + 1,
                "firstFile": {"name": name_a, "start": start_a, "end": end_a},
                "secondFile": {"name": name_b, "start": start_b, "end": end_b},
            }
            for name_a, start_a, end_a, name_b, start_b, end_b in pairs
        ],
    }


def test_parse_report_keys_are_repo_relative(tmp_path):
    clones = _clones_rules.parse_report(
        _payload(("../services/a.py", 10, 17, "src/utils/b.js", 3, 10)),
        base_dir=tmp_path / "src" / "quodeq" / "ui",
        repo_root=tmp_path,
    )
    assert [c.key for c in clones] == [
        "src/quodeq/services/a.py:10-17|src/quodeq/ui/src/utils/b.js:3-10",
    ]


def test_parse_report_key_is_pair_order_independent(tmp_path):
    forward = _clones_rules.parse_report(
        _payload(("../a.py", 1, 5, "../b.py", 9, 13)), base_dir=tmp_path, repo_root=tmp_path.parent,
    )
    reversed_ = _clones_rules.parse_report(
        _payload(("../b.py", 9, 13, "../a.py", 1, 5)), base_dir=tmp_path, repo_root=tmp_path.parent,
    )
    assert [c.key for c in forward] == [c.key for c in reversed_]


def test_parse_report_sorts_and_deduplicates(tmp_path):
    clones = _clones_rules.parse_report(
        _payload(
            ("../z.py", 1, 5, "../y.py", 1, 5),
            ("../a.py", 1, 5, "../b.py", 1, 5),
            ("../b.py", 1, 5, "../a.py", 1, 5),
        ),
        base_dir=tmp_path / "ui",
        repo_root=tmp_path,
    )
    assert [c.key for c in clones] == ["a.py:1-5|b.py:1-5", "y.py:1-5|z.py:1-5"]


def test_parse_report_of_a_clean_tree_is_empty(tmp_path):
    assert _clones_rules.parse_report({"duplicates": []}, base_dir=tmp_path, repo_root=tmp_path) == []


def test_describe_names_the_format_and_size(tmp_path):
    (clone,) = _clones_rules.parse_report(
        _payload(("../a.py", 10, 17, "../b.py", 1, 8)), base_dir=tmp_path, repo_root=tmp_path,
    )
    described = check_clones.describe(clone)
    assert "a.py:10-17" in described and "8 lines" in described and "python" in described


def test_missing_jscpd_reports_how_to_install(tmp_path, monkeypatch, capsys):
    def _boom():
        raise _clones_rules.JscpdUnavailable(_clones_rules.INSTALL_HINT)

    monkeypatch.setattr(check_clones, "_scan", _boom)
    assert check_clones.main([]) == 2
    err = capsys.readouterr().err
    assert "jscpd" in err and "npm install" in err


def test_new_clone_outside_the_baseline_fails_the_gate(tmp_path, monkeypatch, capsys):
    (clone,) = _clones_rules.parse_report(
        _payload(("../a.py", 1, 5, "../b.py", 1, 5)), base_dir=tmp_path / "ui", repo_root=tmp_path,
    )
    baseline = tmp_path / "clones_baseline.txt"
    baseline.write_text("# header\n", encoding="utf-8")
    monkeypatch.setattr(check_clones, "BASELINE_PATH", baseline)
    monkeypatch.setattr(check_clones, "_scan", lambda: [clone])

    assert check_clones.main([]) == 1
    assert "a.py:1-5|b.py:1-5" in capsys.readouterr().out


def test_baselined_clone_passes_the_gate(tmp_path, monkeypatch):
    (clone,) = _clones_rules.parse_report(
        _payload(("../a.py", 1, 5, "../b.py", 1, 5)), base_dir=tmp_path / "ui", repo_root=tmp_path,
    )
    baseline = tmp_path / "clones_baseline.txt"
    monkeypatch.setattr(check_clones, "BASELINE_PATH", baseline)
    monkeypatch.setattr(check_clones, "_scan", lambda: [clone])

    assert check_clones.main(["--update-baseline"]) == 0
    assert check_clones.load_baseline(baseline) == {"a.py:1-5|b.py:1-5"}
    assert check_clones.main([]) == 0


def test_update_baseline_with_no_clones_writes_header_only(tmp_path, monkeypatch):
    baseline = tmp_path / "clones_baseline.txt"
    monkeypatch.setattr(check_clones, "_scan", list)

    assert check_clones.write_baseline(baseline) == 0
    lines = baseline.read_text(encoding="utf-8").splitlines()
    assert lines and all(line.startswith("#") for line in lines)


def test_unknown_argument_is_rejected():
    assert check_clones.main(["--nope"]) == 2


def test_jscpd_command_runs_from_the_ui_package(tmp_path):
    cmd = _clones_rules.jscpd_command(tmp_path, tmp_path / "out")
    assert cmd[:3] == ["npx", "--no-install", "jscpd"]
    assert str(tmp_path / ".jscpd.json") in cmd and "--silent" in cmd
    assert _clones_rules.ui_dir(tmp_path) == tmp_path / "src" / "quodeq" / "ui"


def test_gate_passes_on_current_tree():
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "check_clones.py")],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# Revise DOWNWARD as PR 5 Tasks 2-6 remove each clone; the target is 0.
# NEVER raise without a justification reviewed in the PR that raises it.
BASELINE_CEILING = 91


def test_baseline_only_shrinks():
    count = len(check_clones.load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). "
        "Extract a shared helper instead of grandfathering a new clone."
    )
