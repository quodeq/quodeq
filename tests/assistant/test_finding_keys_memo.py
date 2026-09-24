"""A dismiss/verify draft checks its key against every finding in the run.

That identity set is memoized under a stat stamp of the files it is read
from (eval JSON, evaluation.db and its WAL, events.jsonl), so several drafts
in one turn read them once, while any change to them is seen at once.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.sqlite.assistant_repository import AssistantRepository

_OLD_NS = 1_000_000_000_000_000_000  # 2001-09-09: long settled


class CountingRepo:
    """list_keys-only findings repo that counts reads and can be told to fail."""

    def __init__(self, keys: list[tuple]) -> None:
        self.keys = keys
        self.reads = 0
        self.fail = False

    def list_keys(self) -> list[tuple]:
        self.reads += 1
        if self.fail:
            raise RuntimeError("database disk image is malformed")
        return list(self.keys)


def _age(path: Path, ns: int = _OLD_NS) -> None:
    os.utime(path, ns=(ns, ns))


def _write_eval(run_dir: Path, name: str, lines: list[int]) -> Path:
    path = run_dir / "evaluation" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    violations = [{"req": "R1", "file": "src/a.py", "line": n} for n in lines]
    path.write_text(json.dumps({"violations": violations}), encoding="utf-8")
    _age(path)
    return path


def _ctx(tmp_path: Path, repo: CountingRepo) -> ToolContext:
    eval_root = tmp_path / "evals"
    run_dir = eval_root / "proj" / "run-1"
    run_dir.mkdir(parents=True)
    db = run_dir / "evaluation.db"
    db.touch()
    _age(db)
    store = AssistantRepository(tmp_path / "assistant.db")
    store.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=store, session_id="s1", run_dir=run_dir, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        project_id="proj", reports_dir=eval_root,
        findings_repo_factory=lambda _run_dir: repo,
    )


def _draft(ctx: ToolContext, req: str, file: str, line: int) -> bool:
    out = build_registry(ctx).dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"req": req, "file": file, "line": line, "reason": "guarded above"},
    })
    return out["ok"]


def test_drafts_in_one_turn_read_the_sources_once(tmp_path):
    repo = CountingRepo([("R2", "src/b.py", 7)])
    ctx = _ctx(tmp_path, repo)
    _write_eval(ctx.run_dir, "security.json", [3, 4])

    assert _draft(ctx, "R1", "src/a.py", 3)
    assert _draft(ctx, "R1", "src/a.py", 4)
    assert _draft(ctx, "R2", "src/b.py", 7)
    assert repo.reads == 1


def test_unknown_key_is_still_rejected_from_the_memo(tmp_path):
    ctx = _ctx(tmp_path, CountingRepo([]))
    _write_eval(ctx.run_dir, "security.json", [3])

    assert _draft(ctx, "R1", "src/a.py", 3)
    assert not _draft(ctx, "R1", "src/a.py", 99)


def test_rewritten_eval_json_is_reread(tmp_path):
    ctx = _ctx(tmp_path, CountingRepo([]))
    path = _write_eval(ctx.run_dir, "security.json", [3])
    assert not _draft(ctx, "R1", "src/a.py", 40)

    path.write_text(json.dumps({"violations": [
        {"req": "R1", "file": "src/a.py", "line": 40}]}), encoding="utf-8")
    _age(path, _OLD_NS + 1)

    assert _draft(ctx, "R1", "src/a.py", 40)


def test_new_dimension_file_is_seen(tmp_path):
    ctx = _ctx(tmp_path, CountingRepo([]))
    _write_eval(ctx.run_dir, "security.json", [3])
    assert not _draft(ctx, "R1", "src/a.py", 9)

    _write_eval(ctx.run_dir, "performance.json", [9])

    assert _draft(ctx, "R1", "src/a.py", 9)


def test_changed_database_is_requeried(tmp_path):
    repo = CountingRepo([("R2", "src/b.py", 7)])
    ctx = _ctx(tmp_path, repo)
    assert _draft(ctx, "R2", "src/b.py", 7)

    repo.keys = [("R3", "src/c.py", 1)]
    db = ctx.run_dir / "evaluation.db"
    db.write_bytes(b"x")
    _age(db)

    assert _draft(ctx, "R3", "src/c.py", 1)
    assert not _draft(ctx, "R2", "src/b.py", 7)


def test_corrupt_dimension_file_is_not_memoized(tmp_path):
    repo = CountingRepo([("R2", "src/b.py", 7)])
    ctx = _ctx(tmp_path, repo)
    bad = ctx.run_dir / "evaluation" / "security.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{truncated", encoding="utf-8")
    _age(bad)

    assert _draft(ctx, "R2", "src/b.py", 7)
    assert _draft(ctx, "R2", "src/b.py", 7)
    assert repo.reads == 2


def test_unreadable_database_is_retried(tmp_path):
    repo = CountingRepo([("R2", "src/b.py", 7)])
    repo.fail = True
    ctx = _ctx(tmp_path, repo)
    assert not _draft(ctx, "R2", "src/b.py", 7)

    repo.fail = False

    assert _draft(ctx, "R2", "src/b.py", 7)


def test_recently_written_sources_are_not_memoized(tmp_path):
    repo = CountingRepo([])
    ctx = _ctx(tmp_path, repo)
    path = _write_eval(ctx.run_dir, "security.json", [3])
    _age(path, time.time_ns())

    assert _draft(ctx, "R1", "src/a.py", 3)
    assert _draft(ctx, "R1", "src/a.py", 3)
    assert repo.reads == 2


def test_same_size_rewrite_with_new_inode_is_reread(tmp_path):
    ctx = _ctx(tmp_path, CountingRepo([]))
    path = _write_eval(ctx.run_dir, "security.json", [3])
    assert not _draft(ctx, "R1", "src/a.py", 40)

    # Same byte length as the original, different content, and rewritten via
    # replace-over-original so the file gets a new inode. If mtime happened
    # to land on the same value too, a (name, mtime, size) stamp alone would
    # not see the change; the inode must.
    old_bytes = path.read_bytes()
    new_text = json.dumps({"violations": [
        {"req": "R1", "file": "src/a.py", "line": 40}]}, separators=(",", ": "))
    new_bytes = new_text.encode("utf-8").ljust(len(old_bytes), b" ")
    assert len(new_bytes) == len(old_bytes)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(new_bytes)
    os.replace(tmp, path)
    _age(path)  # same mtime as before the rewrite

    assert _draft(ctx, "R1", "src/a.py", 40)


def test_events_jsonl_change_forces_a_recheck(tmp_path):
    # events.jsonl is one of the stamped sources even though its content is
    # never parsed for keys here; touching it must still bust the memo.
    repo = CountingRepo([("R2", "src/b.py", 7)])
    ctx = _ctx(tmp_path, repo)
    assert _draft(ctx, "R2", "src/b.py", 7)
    assert repo.reads == 1

    events = ctx.run_dir / "events.jsonl"
    events.write_text('{"type": "note"}\n', encoding="utf-8")
    _age(events, _OLD_NS + 1)

    assert _draft(ctx, "R2", "src/b.py", 7)
    assert repo.reads == 2


def test_memo_is_per_run(tmp_path):
    first = _ctx(tmp_path / "one", CountingRepo([]))
    _write_eval(first.run_dir, "security.json", [3])
    second = _ctx(tmp_path / "two", CountingRepo([]))
    _write_eval(second.run_dir, "security.json", [5])

    assert _draft(first, "R1", "src/a.py", 3)
    assert not _draft(second, "R1", "src/a.py", 3)
    assert _draft(second, "R1", "src/a.py", 5)
