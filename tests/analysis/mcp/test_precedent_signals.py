"""precedent_signals: the dismissed-findings facts a findings router downweights against."""
from __future__ import annotations

import quodeq.analysis.mcp.precedent_signals as module
from quodeq.analysis.mcp.precedent_signals import precedent_signals


class _Sink:
    def __init__(self):
        self.warnings: list[str] = []

    def warning(self, msg):
        self.warnings.append(msg)


def _fake_loaders(monkeypatch, calls):
    monkeypatch.setattr(module, "load_precedent_fingerprints", lambda p, **kw: calls.append(("fp", p)) or {"fp"})
    monkeypatch.setattr(module, "load_precedent_corpus", lambda p, r, *, settings: calls.append(("corpus", p, r)) or "corpus")
    monkeypatch.setattr(module, "precedent_match_hook", lambda p, *, log: calls.append(("hook", p, log)) or "hook")


def test_without_a_project_there_is_nothing_to_load(monkeypatch):
    calls: list = []
    _fake_loaders(monkeypatch, calls)
    sink = _Sink()
    assert precedent_signals(None, None, log=sink) == {
        "precedent_fingerprints": set(), "precedent_corpus": None, "on_precedent_match": "hook",
    }
    assert calls == [("hook", None, sink)]


def test_with_a_project_and_run_all_three_are_loaded_in_order(monkeypatch, tmp_path):
    calls: list = []
    _fake_loaders(monkeypatch, calls)
    sink = _Sink()
    run_dir = tmp_path / "run-1"
    assert precedent_signals(tmp_path, run_dir, log=sink) == {
        "precedent_fingerprints": {"fp"}, "precedent_corpus": "corpus", "on_precedent_match": "hook",
    }
    assert calls == [("fp", tmp_path), ("corpus", tmp_path, run_dir), ("hook", tmp_path, sink)]


def test_without_a_run_dir_there_is_no_corpus(monkeypatch, tmp_path):
    calls: list = []
    _fake_loaders(monkeypatch, calls)
    assert precedent_signals(tmp_path, None)["precedent_corpus"] is None
    assert [c[0] for c in calls] == ["fp", "hook"]


def test_the_default_log_is_the_null_sink(monkeypatch, tmp_path):
    from quodeq.core.observability import NULL_LOG

    calls: list = []
    _fake_loaders(monkeypatch, calls)
    precedent_signals(tmp_path, tmp_path / "run-1")
    assert calls[-1] == ("hook", tmp_path, NULL_LOG)
