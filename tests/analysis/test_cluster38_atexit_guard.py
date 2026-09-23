"""AtexitGuard.deregister needs no exception guard."""
from __future__ import annotations

from quodeq.analysis._run_lifecycle_support import AtexitGuard


def test_deregister_after_register_is_idempotent() -> None:
    guard = AtexitGuard(lambda: None)
    guard.register()
    guard.deregister()
    guard.deregister()  # second call: _registered is False, nothing happens
    assert guard._registered is False


def test_deregister_of_never_registered_callback_does_not_raise() -> None:
    guard = AtexitGuard(lambda: None)
    guard._registered = True  # simulate a lost registration
    guard.deregister()  # atexit.unregister of an unknown callable is a no-op
    assert guard._registered is False
