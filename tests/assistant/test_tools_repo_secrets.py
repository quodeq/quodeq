"""The assistant's repo tools keep credentials from the model the way scans do.

One rule decides which files are credential files (``core.secret_files``) and
one redaction masks what an ordinary file holds (``core.secret_scan``).
"""
from __future__ import annotations

import pytest

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.core.secret_files import SECRET_FILE_GLOBS
from quodeq.data.sqlite.assistant_repository import AssistantRepository
from tests.core._fake_secrets import AWS_KEY, GENERIC_VALUE, PEM


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    return root


@pytest.fixture()
def registry(tmp_path, repo):
    store = AssistantRepository(tmp_path / "assistant.db")
    store.create_session(session_id="s1", provider="ollama")
    return build_registry(ToolContext(
        repository=store, session_id="s1", run_dir=None, repo_root=repo,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
    ))


def _read(registry, path):
    return registry.dispatch("read_repo_file", {"path": path})


@pytest.mark.parametrize("name", [
    ".git-credentials", ".pgpass", ".htpasswd", "release.jks", "id_dsa", "id_ecdsa", "prod.env",
    ".env", ".env.production", "server.pem", "TLS.KEY", ".npmrc", "id_ed25519",
])
def test_a_credential_file_is_refused(registry, repo, name):
    (repo / name).write_text("machine example.com login me\n")
    out = _read(registry, name)
    assert out["ok"] is False and "denylist" in out["error"]


@pytest.mark.parametrize("glob", SECRET_FILE_GLOBS)
def test_every_shared_rule_is_refused(registry, repo, glob):
    """No second list: whatever scans treat as a credential file, the assistant refuses."""
    name = glob.replace("*", "local")
    (repo / name).write_text("x\n")
    assert _read(registry, name)["ok"] is False


@pytest.mark.parametrize("name", [".envrc", ".env-production", ".env_local"])
def test_names_the_assistant_used_to_refuse_stay_refused(registry, repo, name):
    (repo / name).write_text(f"export API_TOKEN={GENERIC_VALUE}\n")
    assert _read(registry, name)["ok"] is False


@pytest.mark.parametrize("name", [
    "id_rsa_old", "id_ed25519.bak", ".netrc.bak", ".pgpass.old", ".git-credentials.orig",
    ".htpasswd-staging", ".npmrc.backup", ".pypirc~",
])
def test_a_backup_copy_of_a_credential_file_is_refused(registry, repo, name):
    (repo / name).write_text("machine example.com login me\n")
    assert _read(registry, name)["ok"] is False


@pytest.mark.parametrize("name", ["id_rsa.pub", ".netrc.example", ".npmrc.dist"])
def test_a_public_key_or_template_is_readable(registry, repo, name):
    (repo / name).write_bytes(b"nothing secret\n")
    out = _read(registry, name)
    assert out["ok"] and out["result"]["content"] == "nothing secret\n"


def test_a_link_to_a_credential_file_is_refused(registry, repo):
    (repo / ".env").write_text("A=1\n")
    try:
        (repo / "settings.txt").symlink_to(repo / ".env")
    except OSError:
        pytest.skip("symlinks are not available here")
    assert _read(registry, "settings.txt")["ok"] is False


def test_a_template_is_readable_like_in_a_scan(registry, repo):
    (repo / ".env.example").write_bytes(b"API_TOKEN=changeme\n")
    out = _read(registry, ".env.example")
    assert out["ok"] and out["result"]["content"] == "API_TOKEN=changeme\n"


def test_source_reaches_the_model_redacted(registry, repo):
    body = f"import os\nKEY = '{AWS_KEY}'\n{PEM}\nDB_PASSWORD={GENERIC_VALUE}\nprint(KEY)\n"
    (repo / "settings.py").write_bytes(body.encode())
    result = _read(registry, "settings.py")["result"]
    content = result["content"]
    assert AWS_KEY not in content and "MIIEow" not in content and GENERIC_VALUE not in content
    assert "KEY = '<REDACTED:aws_access_key>'" in content
    assert content.count("\n") == body.count("\n")  # line numbers still match the file
    assert result["redacted"] is True


def test_clean_source_is_returned_as_it_is(registry, repo):
    (repo / "app.py").write_bytes(b"print('hi')\n")
    result = _read(registry, "app.py")["result"]
    assert (result["content"], result["redacted"]) == ("print('hi')\n", False)
