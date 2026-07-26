"""SQLiteStateStore can hold one connection across many operations."""
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.data.sqlite import connection as connection_mod


def test_held_connection_reused_for_all_methods(tmp_path, monkeypatch):
    store = SQLiteStateStore(tmp_path)
    opens = []
    real_open = connection_mod.open_evaluation_db

    def counting_open(run_dir):
        opens.append(run_dir)
        return real_open(run_dir)

    # state_store imports open_evaluation_db by name; patch it there.
    monkeypatch.setattr(
        "quodeq.data.sqlite.state_store.open_evaluation_db", counting_open
    )
    with store.connection():
        for i in range(10):
            store.save_actions_projected_size(i)
        assert store.get_actions_projected_size() == 9
    assert len(opens) == 1  # one open for the whole block


def test_methods_still_work_without_held_connection(tmp_path):
    store = SQLiteStateStore(tmp_path)
    store.save_actions_projected_size(123)
    assert store.get_actions_projected_size() == 123


def test_held_connection_released_after_exit(tmp_path, monkeypatch):
    store = SQLiteStateStore(tmp_path)
    with store.connection():
        pass
    opens = []
    real_open = connection_mod.open_evaluation_db
    monkeypatch.setattr(
        "quodeq.data.sqlite.state_store.open_evaluation_db",
        lambda run_dir: (opens.append(run_dir), real_open(run_dir))[1],
    )
    store.save_actions_projected_size(1)  # must open its own again
    assert len(opens) == 1
