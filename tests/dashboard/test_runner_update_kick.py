from quodeq.dashboard import runner


def test_kick_update_check_calls_check_async(monkeypatch) -> None:
    called = {"v": False}
    monkeypatch.setattr("quodeq.update.checker.check_async", lambda *a, **k: called.__setitem__("v", True))
    runner._kick_update_check()
    assert called["v"] is True


def test_kick_update_check_is_fail_silent(monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("nope")

    monkeypatch.setattr("quodeq.update.checker.check_async", boom)
    runner._kick_update_check()  # must not raise
