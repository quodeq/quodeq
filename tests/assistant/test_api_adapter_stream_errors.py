"""Reader-thread error handling for the streamed API adapter: split out of
``test_api_adapter.py`` to keep that file under the size ratchet.

``_drain`` (the reader-thread body) catches the SDK/transport's own
exception types itself now, rather than letting every exception fall
through to the reader thread's ``run_isolated`` boundary. These two tests
pin the resulting split: an expected SDK/transport error (in particular the
one a cancel's kill hook causes by closing the client mid-read) produces no
WARNING, while a genuine bug in the reader loop still does.
"""
import logging

import httpx
import pytest

from quodeq.assistant.adapters.api import run_api_turn
from quodeq.assistant.cancel import CancelToken, TurnCancelled

from ._api_adapter_helpers import ClosableFakeClient, _config, _delta, _session

_LOGGER_NAME = "quodeq.assistant.adapters.api"


def test_closed_client_read_error_during_cancel_is_not_logged(caplog):
    # The kill hook closes the httpx client to interrupt a stalled read; the
    # reader thread's blocking read then raises httpx's own error type. That
    # is the stop succeeding, not a reader bug, so it must reach the consumer
    # as TurnCancelled without a WARNING from the reader thread's boundary.
    token = CancelToken()

    def dying_stream():
        yield _delta("Hel")
        raise httpx.ReadError("connection closed mid-read")

    client = ClosableFakeClient([dying_stream()])

    def emit(frame):
        token.cancel()

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        with pytest.raises(TurnCancelled) as exc:
            run_api_turn(messages=[{"role": "user", "content": "hi"}],
                         config=_config(), session=_session(emit, cancel=token),
                         client_factory=lambda c: client)
    assert exc.value.partial == "Hel"
    assert caplog.records == []


def test_unexpected_reader_bug_is_still_logged_with_traceback(caplog):
    # A bug in the reader loop itself (not an SDK/transport error) is not
    # something the consumer or the turn boundary knows how to handle, so it
    # still goes through the reader thread's own run_isolated and is logged
    # here, with a traceback, same as before this change.
    def dying_stream():
        yield _delta("Hel")
        raise RuntimeError("reader bug")

    client = ClosableFakeClient([dying_stream()])
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        with pytest.raises(RuntimeError, match="reader bug"):
            run_api_turn(messages=[{"role": "user", "content": "hi"}],
                         config=_config(), session=_session(lambda f: None),
                         client_factory=lambda c: client)
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert warnings[0].exc_info is not None
