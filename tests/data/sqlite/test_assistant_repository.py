from quodeq.data.sqlite.assistant_repository import AssistantRepository


def _repo(tmp_path):
    return AssistantRepository(tmp_path / "assistant.db")


def test_db_path_exposed(tmp_path):
    assert AssistantRepository(tmp_path / "a.db").db_path == tmp_path / "a.db"


def test_create_and_get_session(tmp_path):
    repo = _repo(tmp_path)
    created = repo.create_session(session_id="s1", provider="ollama", model="qwen3")
    assert created["id"] == "s1"
    got = repo.get_session("s1")
    assert got["provider"] == "ollama"
    assert got["model"] == "qwen3"
    assert got["cli_session_id"] is None
    assert repo.get_session("missing") is None


def test_create_session_stores_project_id(tmp_path):
    repo = _repo(tmp_path)
    repo.create_session(session_id="s1", provider="ollama", project_id="selectives")
    assert repo.get_session("s1")["project_id"] == "selectives"


def test_messages_roundtrip_in_order(tmp_path):
    repo = _repo(tmp_path)
    repo.create_session(session_id="s1", provider="ollama")
    repo.add_message("s1", "user", "hello")
    repo.add_message("s1", "assistant", "hi there")
    msgs = repo.list_messages("s1")
    assert [(m["role"], m["content"]) for m in msgs] == [
        ("user", "hello"),
        ("assistant", "hi there"),
    ]


def test_action_lifecycle(tmp_path):
    repo = _repo(tmp_path)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(
        action_id="a1",
        session_id="s1",
        action_type="create_standard",
        payload={"id": "std-x", "name": "X"},
        content_hash="deadbeef",
    )
    action = repo.get_action("a1")
    assert action["status"] == "drafted"
    assert action["payload"] == {"id": "std-x", "name": "X"}
    repo.set_action_status("a1", "applied")
    assert repo.get_action("a1")["status"] == "applied"


def test_events_append_and_tail(tmp_path):
    repo = _repo(tmp_path)
    repo.create_session(session_id="s1", provider="ollama")
    s1 = repo.append_event("s1", {"type": "token", "text": "he"})
    s2 = repo.append_event("s1", {"type": "done"})
    assert s2 > s1
    rows = repo.events_after("s1", after_seq=s1)
    assert rows == [(s2, {"type": "done"})]
    assert repo.events_after("s1", after_seq=s2) == []


def test_set_cli_session_id(tmp_path):
    repo = _repo(tmp_path)
    repo.create_session(session_id="s1", provider="claude")
    repo.set_cli_session_id("s1", "uuid-123")
    assert repo.get_session("s1")["cli_session_id"] == "uuid-123"


def test_set_action_status_conditional_transition_is_atomic(tmp_path):
    """A guarded transition wins exactly once, so a double apply can't
    double-run the side effect. Without expected=, the write is unconditional
    (back-compat)."""
    repo = _repo(tmp_path)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(
        action_id="a1", session_id="s1", action_type="create_standard",
        payload={"id": "x"}, content_hash="h",
    )
    # First claim of drafted -> applied wins.
    assert repo.set_action_status("a1", "applied", expected="drafted") is True
    assert repo.get_action("a1")["status"] == "applied"
    # Second claim from drafted loses: the row is no longer drafted.
    assert repo.set_action_status("a1", "applied", expected="drafted") is False
    assert repo.get_action("a1")["status"] == "applied"


def test_set_action_status_unconditional_still_works(tmp_path):
    repo = _repo(tmp_path)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(
        action_id="a1", session_id="s1", action_type="create_standard",
        payload={"id": "x"}, content_hash="h",
    )
    assert repo.set_action_status("a1", "applied") is True
    assert repo.get_action("a1")["status"] == "applied"


def test_list_all_worktrees_returns_every_status(tmp_path):
    repo = _repo(tmp_path)
    for sid, status in [("s1", "active"), ("s2", "applied"), ("s3", "discarded")]:
        repo.create_session(session_id=sid, provider="ollama")
        repo.upsert_worktree(session_id=sid, project_id="p", repo_root="/r",
                             path=f"/w/{sid}", branch=f"b-{sid}")
        if status != "active":
            repo.set_worktree_status(sid, status)
    rows = repo.list_all_worktrees()
    assert {r["session_id"]: r["status"] for r in rows} == {
        "s1": "active", "s2": "applied", "s3": "discarded",
    }


def test_prune_sessions_older_than_cascades(tmp_path):
    import sqlite3
    repo = _repo(tmp_path)
    repo.create_session(session_id="old", provider="ollama")
    repo.add_message("old", "user", "hi")
    repo.append_event("old", {"type": "token", "text": "x"})
    repo.create_session(session_id="new", provider="ollama")
    repo.add_message("new", "user", "yo")

    # Backdate the old session well past any TTL.
    conn = sqlite3.connect(tmp_path / "assistant.db")
    conn.execute("UPDATE sessions SET created_at = '2020-01-01 00:00:00' WHERE id = 'old'")
    conn.commit()
    conn.close()

    removed = repo.prune_sessions_older_than(days=30)
    assert removed == 1
    assert repo.get_session("old") is None
    assert repo.get_session("new") is not None
    # Cascade: the old session's messages and events are gone too.
    assert repo.list_messages("old") == []
    assert repo.events_after("old", after_seq=0) == []
    assert [(m["role"], m["content"]) for m in repo.list_messages("new")] == [("user", "yo")]


def test_prune_sessions_ttl_zero_is_a_noop(tmp_path):
    repo = _repo(tmp_path)
    repo.create_session(session_id="s1", provider="ollama")
    assert repo.prune_sessions_older_than(days=0) == 0
    assert repo.get_session("s1") is not None


def test_create_session_persists_source(tmp_path):
    repo = _repo(tmp_path)
    row = repo.create_session(session_id="s-shared", provider="ollama", source="shared")
    assert row["source"] == "shared"


def test_create_session_source_defaults_to_local(tmp_path):
    repo = _repo(tmp_path)
    row = repo.create_session(session_id="s-local", provider="ollama")
    assert row["source"] == "local"


def test_v3_db_migrates_to_v4_with_local_source(tmp_path):
    import sqlite3
    db = tmp_path / "assistant.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "PRAGMA user_version = 3;"
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, provider TEXT NOT NULL,"
        " model TEXT, project_uuid TEXT, run_id TEXT, project_id TEXT,"
        " cli_session_id TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')));"
        "INSERT INTO sessions (id, provider) VALUES ('old', 'ollama');"
    )
    conn.commit(); conn.close()
    repo = AssistantRepository(db)
    row = repo.get_session("old")
    assert row["source"] == "local"
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    conn.close()
