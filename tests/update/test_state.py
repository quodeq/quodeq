import json
import tempfile
from pathlib import Path

from quodeq.update.state import (
    UpdateState,
    get_update_state_path,
    read_state,
    write_state,
)


def _env(tmp_path: Path) -> dict[str, str]:
    return {"QUODEQ_UPDATE_STATE_PATH": str(tmp_path / "update_state.json")}


def test_path_honors_explicit_env(tmp_path: Path) -> None:
    env = _env(tmp_path)
    assert get_update_state_path(env) == env["QUODEQ_UPDATE_STATE_PATH"]


def test_path_falls_back_to_quodeq_dir(tmp_path: Path) -> None:
    env = {"QUODEQ_DIR": str(tmp_path)}
    assert get_update_state_path(env) == str(tmp_path / "update_state.json")


def test_read_missing_returns_defaults(tmp_path: Path) -> None:
    state = read_state(_env(tmp_path))
    assert state == UpdateState()
    assert state.auto_check_enabled is True
    assert state.disclosed is False


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    env = _env(tmp_path)
    write_state(UpdateState(latest_version="1.5.0", is_security=True, disclosed=True), env)
    state = read_state(env)
    assert state.latest_version == "1.5.0"
    assert state.is_security is True
    assert state.disclosed is True


def test_write_is_atomic_and_creates_parent(tmp_path: Path) -> None:
    env = {"QUODEQ_UPDATE_STATE_PATH": str(tmp_path / "nested" / "update_state.json")}
    write_state(UpdateState(latest_version="2.0.0"), env)
    on_disk = json.loads(Path(env["QUODEQ_UPDATE_STATE_PATH"]).read_text())
    assert on_disk["latest_version"] == "2.0.0"


def test_read_corrupt_file_returns_defaults(tmp_path: Path) -> None:
    env = _env(tmp_path)
    Path(env["QUODEQ_UPDATE_STATE_PATH"]).write_text("{ not json")
    assert read_state(env) == UpdateState()


def test_write_uses_unique_temp_names(tmp_path: Path, monkeypatch) -> None:
    """Regression: a fixed `<path>.tmp` name raced between the dashboard,
    menubar and CLI processes; each write must use its own temp file."""
    env = _env(tmp_path)
    names: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def spy(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        names.append(name)
        return fd, name

    monkeypatch.setattr("quodeq.update.state.tempfile.mkstemp", spy)
    write_state(UpdateState(latest_version="3.0.0"), env)
    write_state(UpdateState(latest_version="3.0.1"), env)

    assert len(names) == 2
    assert names[0] != names[1]
    # Temp files live next to the target (same-filesystem atomic replace)
    # and none uses the old predictable update_state.json.tmp name.
    assert all(Path(n).parent == tmp_path for n in names)
    assert all(not n.endswith("update_state.json.tmp") for n in names)
    # No stray temp files left behind; last write wins.
    assert [p.name for p in tmp_path.iterdir()] == ["update_state.json"]
    assert read_state(env).latest_version == "3.0.1"


def test_write_failure_is_silent_and_cleans_temp(tmp_path: Path, monkeypatch) -> None:
    env = _env(tmp_path)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("quodeq.update.state.os.replace", boom)
    write_state(UpdateState(latest_version="9.9.9"), env)  # must not raise
    assert list(tmp_path.iterdir()) == []
