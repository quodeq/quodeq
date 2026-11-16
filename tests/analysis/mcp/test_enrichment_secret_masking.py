"""enrich_code masks secrets in everything it stores.

The snippet and context it writes become evaluation.db rows, evidence JSONL,
reports, shared publish and SARIF --with-snippets.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis.mcp.enrichment import enrich_code
from tests.core._fake_secrets import AWS_KEY, PEM

_PLACEHOLDER = "<REDACTED:aws_access_key>"


def _read(path: Path) -> str:
    return path.read_text()


def _repo(tmp_path, body):
    (tmp_path / "cfg.py").write_text(body)
    return tmp_path


def _all_text(finding):
    return " ".join(str(finding.get(k) or "") for k in ("snippet", "context", "reason", "w"))


def test_line_snippet_and_context_are_masked(tmp_path):
    repo = _repo(tmp_path, f"import os\n\nKEY = '{AWS_KEY}'\nprint(KEY)\n")
    finding = {"file": "cfg.py", "line": 3, "snippet": f"KEY = '{AWS_KEY}'"}
    enrich_code(finding, repo, _read)

    assert finding["snippet"] == f"KEY = '{_PLACEHOLDER}'"
    assert f">>> KEY = '{_PLACEHOLDER}'" in finding["context"]
    assert AWS_KEY not in _all_text(finding)


def test_a_window_that_starts_inside_a_key_block_is_masked(tmp_path):
    """The window has no BEGIN header left; the file is redacted whole first."""
    body = PEM + "\n" + "\n".join(f"line{i} = {i}" for i in range(12)) + "\n"
    repo = _repo(tmp_path, body)
    finding = {"file": "cfg.py", "line": 8}
    enrich_code(finding, repo, _read)

    assert "MIIEow" not in finding["context"] and "7onLRn" not in finding["context"]
    assert ">>> line3 = 3" in finding["context"], "line numbers must still match the file"


def test_scope_level_snippet_is_masked(tmp_path):
    repo = _repo(tmp_path, f"KEY = '{AWS_KEY}'\n")
    finding = {"file": "cfg.py", "line": 0}
    enrich_code(finding, repo, _read)
    assert finding["snippet"] == f"KEY = '{_PLACEHOLDER}'\n"


def test_the_model_text_is_masked_when_the_file_cannot_be_read(tmp_path):
    finding = {"file": "missing.py", "line": 1, "snippet": f"k = '{AWS_KEY}'",
               "reason": f"The key {AWS_KEY} is hardcoded", "w": "Hardcoded key"}
    enrich_code(finding, tmp_path, _read)
    assert AWS_KEY not in _all_text(finding)
    assert _PLACEHOLDER in finding["reason"]


def test_the_model_text_is_masked_without_a_work_dir():
    finding = {"file": "a.py", "line": 1, "snippet": f"k = '{AWS_KEY}'"}
    enrich_code(finding, None, _read)
    assert finding["snippet"] == f"k = '{_PLACEHOLDER}'"


_ENV_BODY = "DEBUG=true\nSESSION_SEED=hunter2\nSMTP_PASS=correct horse battery\n"
_SECRET_FILE = "<REDACTED:secret_file>"


@pytest.mark.parametrize(("name", "line"), [
    (".env", 2), (".env", 0), ("deploy/prod.env", 3), (".git-credentials", 1), ("certs/server.key", 1),
])
def test_code_is_never_filled_from_a_credential_file(tmp_path, name, line):
    """Injected text can make the agent report a finding on .env; the lines must not be stored."""
    (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text(_ENV_BODY)
    finding = {"file": name, "line": line, "end_line": 40, "reason": "Settings live in the repository"}
    enrich_code(finding, tmp_path, _read)

    assert (finding["snippet"], finding["context"]) == (_SECRET_FILE, "")
    assert (finding["file"], finding["line"], finding["reason"]) == (name, line, "Settings live in the repository")


def test_the_model_s_own_quote_of_a_credential_file_is_dropped(tmp_path):
    finding = {"file": ".env", "line": 2, "snippet": "SESSION_SEED=hunter2", "context": "DEBUG=true\nSESSION_SEED=hunter2"}
    enrich_code(finding, None, _read)
    assert "hunter2" not in _all_text(finding)
    assert finding["snippet"] == _SECRET_FILE


def test_a_link_to_a_credential_file_is_not_filled_either(tmp_path):
    (tmp_path / ".env").write_text(_ENV_BODY)
    try:
        (tmp_path / "settings.txt").symlink_to(tmp_path / ".env")
    except OSError:
        pytest.skip("symlinks are not available here")
    finding = {"file": "settings.txt", "line": 2}
    enrich_code(finding, tmp_path, _read)
    assert finding["snippet"] == _SECRET_FILE


def test_a_template_of_a_credential_file_is_still_filled(tmp_path):
    (tmp_path / ".env.example").write_text("DEBUG=true\nSESSION_SEED=changeme\n")
    finding = {"file": ".env.example", "line": 2}
    enrich_code(finding, tmp_path, _read)
    assert finding["snippet"] == "SESSION_SEED=changeme"
