"""Unit tests and gate for tools/check_env_reads.py: process-environment reads."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_env_reads

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _write(tmp_path: Path, relpath: str, source: str) -> Path:
    f = tmp_path / relpath
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(source, encoding="utf-8")
    return f


def test_gate_passes_on_current_tree():
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "check_env_reads.py")],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_scan_finds_an_environ_read(tmp_path):
    _write(tmp_path, "src/quodeq/api/x.py", "import os\nX = os.environ.get('A')\n")
    hits = check_env_reads.scan_tree(tmp_path / "src")
    assert [(h.path.name, h.line) for h in hits] == [("x.py", 2)]


def test_config_layer_is_allowed(tmp_path):
    for relpath in (
        "src/quodeq/shared/_env.py",
        "src/quodeq/shared/_env_ai.py",
        "src/quodeq/shared/_env_paths.py",
        "src/quodeq/shared/_env_db.py",
        "src/quodeq/shared/_env_embeddings.py",
        "src/quodeq/config/loader.py",
        "src/quodeq/config/nested/deep.py",
        "src/quodeq/_cli_env.py",
    ):
        _write(tmp_path, relpath, "import os\nX = os.environ.get('A')\n")
    assert check_env_reads.scan_tree(tmp_path / "src") == []


def test_every_shared_env_module_is_allowed_but_its_siblings_are_not(tmp_path):
    """The allowlist covers `shared/_env*`, not the rest of `shared/`."""
    _write(tmp_path, "src/quodeq/shared/_env_whatever.py", "import os\nX = os.getenv('A')\n")
    _write(tmp_path, "src/quodeq/shared/frozen.py", "import os\nX = os.getenv('A')\n")
    assert [h.key for h in check_env_reads.scan_tree(tmp_path / "src")] == [
        "src/quodeq/shared/frozen.py:2",
    ]


def test_allowlist_does_not_match_by_prefix(tmp_path):
    """`config_util.py` is not `config/`, and `_envs/` is not a `shared/_env*` file."""
    _write(tmp_path, "src/quodeq/config_util.py", "import os\nX = os.getenv('A')\n")
    _write(tmp_path, "src/quodeq/shared/_envs/deep.py", "import os\nX = os.getenv('A')\n")
    assert sorted(h.key for h in check_env_reads.scan_tree(tmp_path / "src")) == [
        "src/quodeq/config_util.py:2",
        "src/quodeq/shared/_envs/deep.py:2",
    ]


def test_every_form_of_read_is_flagged(tmp_path):
    _write(tmp_path, "src/quodeq/api/forms.py", (
        "import os\n"
        "a = os.environ.get('A')\n"
        "b = os.environ['B']\n"
        "c = os.environ.copy()\n"
        "d = dict(os.environ)\n"
        "e = 'E' in os.environ\n"
        "f = os.getenv('F')\n"
    ))
    assert [h.line for h in check_env_reads.scan_tree(tmp_path / "src")] == [2, 3, 4, 5, 6, 7]


def test_from_os_import_and_module_alias_are_flagged(tmp_path):
    _write(tmp_path, "src/quodeq/api/imported.py", (
        "from os import environ, getenv\n"
        "import os as _os\n"
        "a = environ.get('A')\n"
        "b = getenv('B')\n"
        "c = _os.environ['C']\n"
    ))
    assert [h.line for h in check_env_reads.scan_tree(tmp_path / "src")] == [3, 4, 5]


def test_import_alias_of_environ_is_flagged(tmp_path):
    _write(tmp_path, "src/quodeq/api/aliased.py", (
        "from os import environ as _e\n"
        "a = _e.get('A')\n"
    ))
    assert [h.line for h in check_env_reads.scan_tree(tmp_path / "src")] == [2]


def test_comments_strings_and_unrelated_names_are_not_flagged(tmp_path):
    _write(tmp_path, "src/quodeq/api/clean.py", (
        "import os\n"
        "# os.environ.get('A')\n"
        "DOC = 'use os.getenv(\"B\") instead'\n"
        "def f(environ):\n"
        "    return environ.get('C')\n"
        "class K:\n"
        "    environ = {}\n"
        "p = os.path.join('a', 'b')\n"
    ))
    assert check_env_reads.scan_tree(tmp_path / "src") == []


def test_assignment_to_environ_after_import_is_still_flagged(tmp_path):
    """A write target is not a read, but any load of the name is."""
    _write(tmp_path, "src/quodeq/api/stored.py", (
        "import os\n"
        "os.environ['A'] = '1'\n"
    ))
    assert [h.line for h in check_env_reads.scan_tree(tmp_path / "src")] == [2]


def test_one_key_per_line_even_with_two_reads(tmp_path):
    _write(tmp_path, "src/quodeq/api/two.py", (
        "import os\n"
        "x = os.environ.get('A') or os.getenv('B')\n"
    ))
    assert [h.key for h in check_env_reads.scan_tree(tmp_path / "src")] == ["src/quodeq/api/two.py:2"]


def test_syntax_error_file_is_skipped(tmp_path, capsys):
    _write(tmp_path, "src/quodeq/api/broken.py", "def (:\n")
    assert check_env_reads.scan_tree(tmp_path / "src") == []
    assert "skipping" in capsys.readouterr().err


def test_violation_key_is_relpath_and_line(tmp_path):
    _write(tmp_path, "src/quodeq/api/x.py", "import os\nX = os.getenv('A')\n")
    (hit,) = check_env_reads.scan_tree(tmp_path / "src")
    assert check_env_reads.violation_key(hit) == "src/quodeq/api/x.py:2"
    assert "os.getenv" in check_env_reads.describe(hit)


def test_update_baseline_with_no_violations_writes_header_only(tmp_path, monkeypatch):
    empty = tmp_path / "src"
    empty.mkdir()
    monkeypatch.setattr(check_env_reads, "SRC_ROOT", empty)
    baseline = tmp_path / "env_reads_baseline.txt"

    assert check_env_reads.write_baseline(baseline) == 0
    lines = baseline.read_text(encoding="utf-8").splitlines()
    assert lines and all(line.startswith("#") for line in lines)
    assert check_env_reads.load_baseline(baseline) == set()


def test_no_new_env_read_violations():
    baseline = check_env_reads.load_baseline()
    new = sorted(set(check_env_reads.collect_violations()) - baseline)
    assert new == [], (
        "New process-environment read(s) outside the config layer. Take the "
        "values as an injected `env: Mapping[str, str] | None = None` parameter "
        "(`os.environ if env is None else env`) instead:\n" + "\n".join(new)
    )


def test_baseline_has_no_stale_entries():
    current = set(check_env_reads.collect_violations())
    stale = sorted(check_env_reads.load_baseline() - current)
    assert stale == [], (
        "Baseline lists reads that no longer exist; regenerate with "
        "`python tools/check_env_reads.py --update-baseline`:\n" + "\n".join(stale)
    )


# Revise DOWNWARD as PR 2 Tasks 2-5 make each read injectable; the target is
# 0. NEVER raise without a justification reviewed in the PR that raises it.
BASELINE_CEILING = 94


def test_baseline_only_shrinks():
    count = len(check_env_reads.load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). "
        "Inject the environment instead of grandfathering a new read."
    )
