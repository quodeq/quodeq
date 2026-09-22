"""Copilot MCP policy failures retain their cause across run persistence."""
import json

import pytest

from quodeq._cli_lifecycle import _record_provider_fatal_if_cancelled
from quodeq.analysis._loop_guards import _raise_on_fatal_cancel
from quodeq.analysis._loop_state import _interruption_reason
from quodeq.analysis.errors import REASON_PROVIDER_FATAL, FatalProviderError
from quodeq.analysis.run_lifecycle import RunLifecycleContext
from quodeq.core.stream.events import copilot_error
from quodeq.data.fs.run_status_store import read_status
from quodeq.services.scan_progress import build_scan_progress
from quodeq.shared import cancellation
from quodeq.shared.serialization import to_camel_dict


def _policy_error():
    message, reason = copilot_error({"type": "session.warning", "data": {
        "warningType": "mcp", "message": "1 MCP server was blocked by policy: 'findings'",
    }})
    return FatalProviderError(message, reason=reason)


def test_policy_failure_persists_specific_reason_in_status_and_progress(tmp_path):
    with pytest.raises(FatalProviderError):
        with RunLifecycleContext(tmp_path, "job-1", ["security"]):
            raise _policy_error()

    status = read_status(tmp_path)
    assert status["state"] == "failed"
    assert status["exit_reason"] == "copilot_mcp_policy"
    progress = to_camel_dict(build_scan_progress("job-1", tmp_path, time_limit_s=None))
    assert progress["exitReason"] == "copilot_mcp_policy"
    assert progress["state"] == "failed"


def test_policy_cancellation_keeps_reason_through_loop_failure(tmp_path):
    error = _policy_error()
    cancellation.request_cancel(reason=f"{REASON_PROVIDER_FATAL}:{error.reason}: {error}")
    assert _interruption_reason() == "copilot_mcp_policy"
    assert _interruption_reason(error) == "copilot_mcp_policy"
    with pytest.raises(FatalProviderError) as exc:
        _raise_on_fatal_cancel(tmp_path)
    assert exc.value.reason == "copilot_mcp_policy"


def test_policy_failure_preserves_completed_files_with_specific_warning(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "security_evidence.jsonl").write_text(json.dumps({
        "_marker": "file_done", "file": "example.py", "status": "ok",
    }) + "\n")
    with RunLifecycleContext(tmp_path, "job-1", ["security"]) as lifecycle:
        error = _policy_error()
        cancellation.request_cancel(reason=f"{REASON_PROVIDER_FATAL}:{error.reason}: {error}")
        _raise_on_fatal_cancel(tmp_path)
        _record_provider_fatal_if_cancelled(lifecycle)
    status = read_status(tmp_path)
    assert status["state"] == "done"
    assert status["exit_reason"] == "copilot_mcp_policy"
    assert (evidence / "security_evidence.jsonl").exists()
