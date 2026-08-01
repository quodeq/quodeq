"""Run-directory read mechanics live in the data layer (T1 group C2).

services/_cache counted evaluation/*.json and parsed status.json inline;
services/_accumulated_data walked run dirs for its stat fingerprint. The
mechanics now live in data/fs/run_files.py; the services keep the guard
decisions (terminal-state sets, staleness rules) and delegate the I/O.
"""
from __future__ import annotations

import json


class TestCountEvalFiles:
    def test_missing_dir_returns_none(self, tmp_path):
        from quodeq.data.fs.run_files import count_eval_files

        assert count_eval_files(tmp_path) is None

    def test_empty_dir_returns_zero(self, tmp_path):
        from quodeq.data.fs.run_files import count_eval_files

        (tmp_path / "evaluation").mkdir()
        assert count_eval_files(tmp_path) == 0

    def test_counts_only_json(self, tmp_path):
        from quodeq.data.fs.run_files import count_eval_files

        d = tmp_path / "evaluation"
        d.mkdir()
        (d / "a.json").write_text("{}")
        (d / "b.json").write_text("{}")
        (d / "notes.txt").write_text("x")
        assert count_eval_files(tmp_path) == 2


class TestReadRunState:
    def test_missing_returns_none(self, tmp_path):
        from quodeq.data.fs.run_files import read_run_state

        assert read_run_state(tmp_path) is None

    def test_corrupt_returns_none(self, tmp_path):
        from quodeq.data.fs.run_files import read_run_state

        (tmp_path / "status.json").write_text("{nope")
        assert read_run_state(tmp_path) is None

    def test_non_dict_returns_none(self, tmp_path):
        from quodeq.data.fs.run_files import read_run_state

        (tmp_path / "status.json").write_text("[1]")
        assert read_run_state(tmp_path) is None

    def test_returns_state_string(self, tmp_path):
        from quodeq.data.fs.run_files import read_run_state

        (tmp_path / "status.json").write_text(json.dumps({"state": "running"}))
        assert read_run_state(tmp_path) == "running"


class TestRunFingerprint:
    def test_changes_when_inputs_change(self, tmp_path):
        from quodeq.data.fs.run_files import run_fingerprint

        (tmp_path / "evaluation").mkdir()
        (tmp_path / "evaluation" / "a.json").write_text("{}")
        before = run_fingerprint(tmp_path)
        assert before == run_fingerprint(tmp_path)  # stable

        (tmp_path / "evaluation" / "a.json").write_text('{"changed": true}')
        assert run_fingerprint(tmp_path) != before

    def test_empty_run_dir_is_stable(self, tmp_path):
        from quodeq.data.fs.run_files import run_fingerprint

        assert run_fingerprint(tmp_path) == run_fingerprint(tmp_path)


def test_accumulated_data_reexports_run_fingerprint():
    """Facade compat: the service module keeps exposing run_fingerprint."""
    from quodeq.data.fs.run_files import run_fingerprint as data_fn
    from quodeq.services._accumulated_data import run_fingerprint as svc_fn

    assert svc_fn is data_fn
