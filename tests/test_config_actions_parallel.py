from codecompass.config.actions import resolve_parallel


def test_resolve_parallel_defaults_unlimited():
    assert resolve_parallel(None, False) == 0


def test_resolve_parallel_sequential_forces_one():
    assert resolve_parallel(None, True) == 1


def test_resolve_parallel_parses_int():
    assert resolve_parallel("4", False) == 4
