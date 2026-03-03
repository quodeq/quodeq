from __future__ import annotations

from pathlib import Path

import pytest

from codecompass.v2.engine.file_sampler import sample_files, SampledFile
from codecompass.v2.engine.finding import Finding


def _make_source_tree(tmp_path: Path) -> Path:
    """Create a source tree with various files."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("from flask import Flask\napp = Flask(__name__)\n\n@app.route('/')\ndef index():\n    return 'hello'\n")
    (src / "config.py").write_text("SECRET_KEY = 'changeme'\nDEBUG = True\n")
    (src / "utils.py").write_text("def helper():\n    pass\n")
    (src / "main.py").write_text("if __name__ == '__main__':\n    print('hi')\n")

    sub = src / "handlers"
    sub.mkdir()
    (sub / "auth.py").write_text("def login(user, password):\n    return True\n")
    (sub / "api.py").write_text("def get_users():\n    return []\n")
    (sub / "data.py").write_text("x = 1\n")

    return src


def test_sample_files_basic(tmp_path):
    src = _make_source_tree(tmp_path)
    findings = []
    sampled = sample_files(src, findings, {".py"}, max_files=20)
    assert len(sampled) > 0
    assert all(isinstance(sf, SampledFile) for sf in sampled)


def test_detector_finding_files_prioritized(tmp_path):
    src = _make_source_tree(tmp_path)
    findings = [
        Finding(rule="r1", label="test", file=str(src / "utils.py"), dimension="security", detector="grep"),
    ]
    sampled = sample_files(src, findings, {".py"}, max_files=20)
    paths = [sf.path for sf in sampled]
    # utils.py should come first because it has a detector finding
    assert paths[0] == "utils.py"
    assert sampled[0].reason == "detector_finding"


def test_high_risk_names_selected(tmp_path):
    src = _make_source_tree(tmp_path)
    sampled = sample_files(src, [], {".py"}, max_files=20)
    reasons = {sf.path: sf.reason for sf in sampled}
    assert reasons.get("config.py") == "high_risk_name"
    assert reasons.get("handlers/auth.py") == "high_risk_name"
    assert reasons.get("handlers/api.py") == "high_risk_name"


def test_entry_points_detected(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    # Use names that are NOT in _HIGH_RISK_NAMES so they get classified as entry_point
    (src / "cli.py").write_text("if __name__ == '__main__':\n    print('hi')\n")
    (src / "web.py").write_text("from flask import Flask\napp = Flask(__name__)\n")
    (src / "utils.py").write_text("def helper():\n    pass\n")

    sampled = sample_files(src, [], {".py"}, max_files=20)
    entry_files = [sf.path for sf in sampled if sf.reason == "entry_point"]
    assert "cli.py" in entry_files or "web.py" in entry_files


def test_max_files_limit(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for i in range(30):
        (src / f"mod_{i}.py").write_text(f"x = {i}\n")
    sampled = sample_files(src, [], {".py"}, max_files=5)
    assert len(sampled) == 5


def test_truncation(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    long_content = "\n".join(f"line {i}" for i in range(600))
    (src / "big.py").write_text(long_content)
    sampled = sample_files(src, [], {".py"}, max_files=5, max_lines=100)
    assert len(sampled) == 1
    assert sampled[0].truncated is True
    assert sampled[0].lines == 600
    assert "truncated" in sampled[0].content


def test_skip_dirs(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "good.py").write_text("x = 1\n")
    venv = src / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "bad.py").write_text("y = 2\n")
    node = src / "node_modules" / "pkg"
    node.mkdir(parents=True)
    (node / "index.py").write_text("z = 3\n")

    sampled = sample_files(src, [], {".py"}, max_files=20)
    paths = [sf.path for sf in sampled]
    assert "good.py" in paths
    assert not any(".venv" in p for p in paths)
    assert not any("node_modules" in p for p in paths)


def test_extension_filter(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("x = 1\n")
    (src / "app.js").write_text("x = 1;\n")
    (src / "readme.md").write_text("# hi\n")

    sampled = sample_files(src, [], {".py"}, max_files=20)
    paths = [sf.path for sf in sampled]
    assert "app.py" in paths
    assert "app.js" not in paths
    assert "readme.md" not in paths


def test_empty_src(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    sampled = sample_files(src, [], {".py"}, max_files=20)
    assert sampled == []


def test_finding_with_relative_path(tmp_path):
    src = _make_source_tree(tmp_path)
    # Finding with absolute path that should be resolved relative to src
    findings = [
        Finding(rule="r1", label="test", file=str(src / "utils.py"), dimension="security", detector="grep"),
    ]
    sampled = sample_files(src, findings, {".py"}, max_files=20)
    detector_files = [sf for sf in sampled if sf.reason == "detector_finding"]
    assert len(detector_files) == 1
    assert detector_files[0].path == "utils.py"
