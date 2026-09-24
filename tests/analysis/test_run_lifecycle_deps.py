"""RunLifecycleContext's collaborators can be injected via LifecycleDeps."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.run_lifecycle import LifecycleDeps, RunLifecycleContext


class _Stub:
    def __init__(self, *a, **k):
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self, *a, **k):
        self.stopped = True


def test_injected_collaborators_are_used(tmp_path: Path):
    writes = []
    hb, rs = [], []

    def heartbeat(run_dir):
        hb.append(_Stub())
        return hb[-1]

    def resources():
        rs.append(_Stub())
        return rs[-1]

    deps = LifecycleDeps(
        write_status=lambda run_dir, status: writes.append(status.state),
        heartbeat_factory=heartbeat, resources_factory=resources,
    )
    with RunLifecycleContext(tmp_path, "ext-x", [], deps=deps):
        pass
    assert writes, "status writes go through the injected writer"
    assert len(hb) == 1 and len(rs) == 1
    assert not (tmp_path / "status.json").exists()
