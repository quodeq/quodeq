"""DI seams for the projection stack: injected stores, engines, and locks.

The projection stack hardcoded ``SQLiteStateStore(run_dir)`` at every layer
and serialized ``ensure_projected`` through a module-global lock dict, so no
test could exercise projection logic without a real SQLite file, and global
lock state leaked between tests. Each collaborator is now injectable with
the concrete default preserved.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from quodeq.data.projection.engine import ProjectionEngine
from quodeq.data.projection.projector import Projector, ProjectionResult


class _FakeStore:
    def __init__(self):
        self.cleared = False
        self.findings = []
        self.checkpoint = None
        self.projected_size = None

    def clear_all(self):
        self.cleared = True

    def get_checkpoint(self):
        return self.checkpoint

    def save_checkpoint(self, ts):
        self.checkpoint = ts

    def save_projected_size(self, n):
        self.projected_size = n

    def get_projected_size(self):
        return self.projected_size

    def get_grades_algo_version(self):
        # Report current so grades_stale stays False — these tests exercise
        # the event/actions projection seams, not grade reconciliation.
        from quodeq.core.scoring.projector_scoring import GRADE_ALGO_VERSION
        return GRADE_ALGO_VERSION

    def save_grades_algo_version(self, version):
        pass

    def record_finding(self, payload):
        self.findings.append(payload)


class _FakeEngine:
    def __init__(self):
        self.calls = []

    def rebuild(self, path, run_dir):
        self.calls.append(("rebuild", path, run_dir))
        return 3

    def update(self, path, run_dir):
        self.calls.append(("update", path, run_dir))
        return 1


def test_engine_uses_injected_store_factory(tmp_path):
    log = tmp_path / "events.jsonl"
    log.write_text("")
    made = []

    def factory(run_dir):
        s = _FakeStore()
        made.append((run_dir, s))
        return s

    ProjectionEngine(store_factory=factory).rebuild(log, tmp_path)

    assert made and made[0][0] == tmp_path
    assert made[0][1].cleared is True
    assert not (tmp_path / "evaluation.db").exists()


def test_projector_rebuild_decision_via_injected_store(tmp_path):
    log = tmp_path / "events.jsonl"
    log.write_text("")

    fresh = _FakeStore()  # checkpoint None -> rebuild
    engine = _FakeEngine()
    res = Projector(engine=engine, store_factory=lambda d: fresh).project(log, tmp_path)
    assert res == ProjectionResult(events_projected=3, rebuilt=True)

    seen = _FakeStore()
    seen.checkpoint = "2026-01-01T00:00:00"
    res2 = Projector(engine=engine, store_factory=lambda d: seen).project(log, tmp_path)
    assert res2 == ProjectionResult(events_projected=1, rebuilt=False)
    assert [c[0] for c in engine.calls] == ["rebuild", "update"]


def test_ensure_lock_registry_serializes_concurrent_acquires_for_same_dir(tmp_path):
    from quodeq.data.projection.projector import EnsureLockRegistry

    reg = EnsureLockRegistry()
    order = []

    def worker(tag):
        with reg.acquire(tmp_path):
            order.append(f"{tag}-enter")
            time.sleep(0.01)
            order.append(f"{tag}-exit")

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    time.sleep(0.002)  # let t1 win the race to acquire first
    t2.start()
    t1.join()
    t2.join()

    # Whichever thread entered first must have exited before the other entered.
    assert order[1] == order[0].replace("enter", "exit")


def test_ensure_lock_registry_drops_entry_after_release(tmp_path):
    from quodeq.data.projection.projector import EnsureLockRegistry

    reg = EnsureLockRegistry()
    with reg.acquire(tmp_path):
        assert len(reg._locks) == 1
    assert len(reg._locks) == 0, "registry must not keep growing after release"


def test_ensure_projected_uses_injected_locks_and_store(tmp_path):
    from quodeq.data.projection.projector import EnsureLockRegistry

    log = tmp_path / "events.jsonl"
    log.write_text("x\n")

    class _SpyRegistry(EnsureLockRegistry):
        def __init__(self):
            super().__init__()
            self.asked = []

        def acquire(self, run_dir):
            self.asked.append(run_dir)
            return super().acquire(run_dir)

    store = _FakeStore()
    store.projected_size = log.stat().st_size  # fresh -> early no-op return
    reg = _SpyRegistry()
    proj = Projector(engine=_FakeEngine(), store_factory=lambda d: store, locks=reg)

    res = proj.ensure_projected(log, tmp_path)

    assert res == ProjectionResult(events_projected=0, rebuilt=False)
    assert reg.asked == [tmp_path]


def test_handlers_do_not_depend_on_concrete_store():
    """Handlers write through the StateStoreWriter protocol; the concrete
    SQLite class must not be a runtime dependency of the handler module."""
    import quodeq.data.projection.handlers as handlers

    assert "SQLiteStateStore" not in vars(handlers)


def test_handle_dispatches_to_duck_typed_store():
    from quodeq.core.events.models import EventType
    from quodeq.data.projection.handlers import handle

    store = _FakeStore()
    ev = SimpleNamespace(event_type=EventType.JUDGMENT_CREATED, payload={"req": "X-1"})
    handle(ev, store)
    assert store.findings == [{"req": "X-1"}]
