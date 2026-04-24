from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from quodeq.shared.logging import log_info


def test_run_log_captures_log_info_during_pipeline(tmp_path: Path, monkeypatch) -> None:
    """log_info calls between install/uninstall must land in run.log."""
    from quodeq.shared.run_log import RunLogHandler, RunLogWriter

    run_dir = tmp_path / "project" / "run-1"
    run_dir.mkdir(parents=True)

    writer = RunLogWriter(run_dir)
    handler = RunLogHandler(writer)
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger("quodeq")
    logger.addHandler(handler)
    try:
        log_info("line-one")
        log_info("line-two")
    finally:
        logger.removeHandler(handler)
        writer.close()

    contents = (run_dir / "run.log").read_text()
    assert "line-one" in contents
    assert "line-two" in contents


def test_pipeline_installs_and_removes_run_log_handler(tmp_path: Path, monkeypatch) -> None:
    """_run_pipeline_with_cleanup must install RunLogHandler on entry and remove on exit."""
    import quodeq._cli_evaluation as cli
    from quodeq.shared.run_log import RunLogHandler

    logger = logging.getLogger("quodeq")
    initial_handlers = set(id(h) for h in logger.handlers)

    # Stub _execute_pipeline so we exercise only the wrapper's install/remove logic.
    with patch.object(cli, "_execute_pipeline", return_value=0), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        evidence_dir = tmp_path / "proj" / "run" / "evidence"
        evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
        evidence_dir.mkdir(parents=True)
        evaluation_dir.mkdir(parents=True)
        import argparse
        args = argparse.Namespace(repo="local")
        inputs = type("I", (), {"src": tmp_path, "language": "python", "manifest": None, "dims_data": None})()

        # During pipeline, a RunLogHandler must be attached to the quodeq logger.
        attached: list[bool] = []
        def _spy(*a, **k):
            attached.append(any(isinstance(h, RunLogHandler) for h in logger.handlers))
            return 0
        with patch.object(cli, "_execute_pipeline", side_effect=_spy):
            cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    assert attached == [True]
    # After exit, no stray RunLogHandler remains.
    assert not any(isinstance(h, RunLogHandler) for h in logger.handlers)
    assert set(id(h) for h in logger.handlers) == initial_handlers
