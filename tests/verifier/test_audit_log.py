import json
from pathlib import Path

from quodeq.resolver.models import (
    FindingInput,
    FunctionInfo,
    Location,
    Manifest,
)
from quodeq.verifier.audit_log import write_audit_log


def _manifest() -> Manifest:
    return Manifest(
        target_file="src/api/app.py",
        target_line=6,
        target_file_role="composition_root",
        referenced_symbol="FilesystemActionProvider",
        referenced_symbol_defined_at=Location("src/services/filesystem.py", 39),
    )


def test_audit_log_writes_four_files(tmp_path: Path):
    write_audit_log(
        root=tmp_path,
        verification_id="v1",
        manifest=_manifest(),
        system_prompt="SYSTEM",
        user_prompt="USER",
        raw_response={"foo": "bar"},
    )
    log_dir = tmp_path / "v1"
    assert (log_dir / "manifest.json").exists()
    assert (log_dir / "prompt.system.txt").exists()
    assert (log_dir / "prompt.user.txt").exists()
    assert (log_dir / "response.json").exists()


def test_audit_log_files_are_readable(tmp_path: Path):
    write_audit_log(
        root=tmp_path,
        verification_id="v2",
        manifest=_manifest(),
        system_prompt="hello",
        user_prompt="world",
        raw_response={"answer": 42},
    )
    log_dir = tmp_path / "v2"
    assert (log_dir / "prompt.system.txt").read_text() == "hello"
    assert (log_dir / "prompt.user.txt").read_text() == "world"
    assert json.loads((log_dir / "response.json").read_text()) == {"answer": 42}
    assert "src/api/app.py" in (log_dir / "manifest.json").read_text()


def test_audit_log_overwrites_existing_files(tmp_path: Path):
    write_audit_log(
        root=tmp_path,
        verification_id="v3",
        manifest=_manifest(),
        system_prompt="first",
        user_prompt="first",
        raw_response={"first": True},
    )
    write_audit_log(
        root=tmp_path,
        verification_id="v3",
        manifest=_manifest(),
        system_prompt="second",
        user_prompt="second",
        raw_response={"second": True},
    )
    log_dir = tmp_path / "v3"
    assert (log_dir / "prompt.system.txt").read_text() == "second"
    assert json.loads((log_dir / "response.json").read_text()) == {"second": True}
