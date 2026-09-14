"""Unit tests for check_fault_tolerance.py's pure except-handler classification."""
import ast

import check_fault_tolerance as cft


def _handler(src: str) -> ast.ExceptHandler:
    """Parse a one-handler try/except snippet and return its ExceptHandler node."""
    tree = ast.parse(src)
    try_node = tree.body[0]
    assert isinstance(try_node, ast.Try)
    assert len(try_node.handlers) == 1
    return try_node.handlers[0]


def test_bare_except_is_flagged():
    h = _handler("try:\n    f()\nexcept:\n    pass\n")
    assert cft._handler_kind(h) == "bare-except"


def test_empty_except_pass_is_flagged():
    h = _handler("try:\n    f()\nexcept ValueError:\n    pass\n")
    assert cft._handler_kind(h) == "empty-except"


def test_broad_exception_without_reraise_is_flagged():
    h = _handler("try:\n    f()\nexcept Exception:\n    log.warning('x')\n")
    assert cft._handler_kind(h) == "broad-except"


def test_broad_base_exception_without_reraise_is_flagged():
    h = _handler("try:\n    f()\nexcept BaseException:\n    log.warning('x')\n")
    assert cft._handler_kind(h) == "broad-except"


def test_broad_exception_that_reraises_is_not_flagged():
    h = _handler("try:\n    f()\nexcept Exception:\n    log.warning('x')\n    raise\n")
    assert cft._handler_kind(h) is None


def test_broad_exception_via_qualified_attribute_is_flagged():
    h = _handler("try:\n    f()\nexcept builtins.Exception:\n    log.warning('x')\n")
    assert cft._handler_kind(h) == "broad-except"


def test_broad_exception_inside_tuple_is_flagged():
    h = _handler(
        "try:\n    f()\nexcept (ValueError, Exception):\n    log.warning('x')\n"
    )
    assert cft._handler_kind(h) == "broad-except"


def test_specific_exception_with_body_is_not_flagged():
    h = _handler("try:\n    f()\nexcept ValueError as e:\n    log.warning(str(e))\n")
    assert cft._handler_kind(h) is None


def test_tuple_of_specific_exceptions_is_not_flagged():
    h = _handler(
        "try:\n    f()\nexcept (ValueError, KeyError):\n    log.warning('x')\n"
    )
    assert cft._handler_kind(h) is None


def test_empty_except_ellipsis_is_flagged():
    h = _handler("try:\n    f()\nexcept ValueError:\n    ...\n")
    assert cft._handler_kind(h) == "empty-except"


def test_empty_except_docstring_is_flagged():
    h = _handler('try:\n    f()\nexcept ValueError:\n    "ignored"\n')
    assert cft._handler_kind(h) == "empty-except"


def test_empty_except_double_pass_is_flagged():
    h = _handler("try:\n    f()\nexcept ValueError:\n    pass\n    pass\n")
    assert cft._handler_kind(h) == "empty-except"


def _kinds(src: str) -> list[tuple[int, str]]:
    """Scan a source snippet the way the ratchet scans a file; return (lineno, kind)."""
    return [(lineno, kind) for _rel, lineno, kind in cft._scan_tree(ast.parse(src), "x.py")]


def test_contextlib_suppress_is_flagged():
    assert _kinds("with contextlib.suppress(OSError):\n    f()\n") == [(1, "suppress")]


def test_bare_suppress_is_flagged():
    assert _kinds("with suppress(OSError):\n    f()\n") == [(1, "suppress")]


def test_plain_open_is_not_flagged():
    assert _kinds("with open('x') as fh:\n    f(fh)\n") == []


def test_async_with_suppress_is_flagged():
    src = "async def g():\n    async with contextlib.suppress(OSError):\n        await f()\n"
    assert _kinds(src) == [(2, "suppress")]


def test_aliased_module_suppress_is_flagged():
    # Any `X.suppress(...)`, since contextlib can be imported under an alias.
    assert _kinds("with cl.suppress(OSError):\n    f()\n") == [(1, "suppress")]


# Post-PR review M3: suppress() is flagged wherever it is CALLED, not only as
# a direct `with` item, so the two evasions the review probed are closed.

def test_suppress_via_exit_stack_is_flagged():
    src = "with ExitStack() as stack:\n    stack.enter_context(contextlib.suppress(OSError))\n    f()\n"
    assert _kinds(src) == [(2, "suppress")]


def test_suppress_bound_to_a_name_first_is_flagged():
    src = "cm = contextlib.suppress(OSError)\nwith cm:\n    f()\n"
    assert _kinds(src) == [(1, "suppress")]


def test_suppress_is_keyed_once_per_call_site():
    # The `with` line and the call are the same line; one entry, not two.
    src = "with contextlib.suppress(OSError), open('x') as fh:\n    f(fh)\n"
    assert _kinds(src) == [(1, "suppress")]


# Post-PR review M3: `_reraises` is a reachability-aware scan of the handler's
# top level, so a `raise` that can never run does not launder a broad catch.

def test_unreachable_raise_after_return_does_not_count_as_reraise():
    h = _handler(
        "try:\n    f()\nexcept Exception:\n    log.warning('x')\n    return None\n    raise\n"
    )
    assert cft._handler_kind(h) == "broad-except"


def test_raise_inside_a_branch_is_still_conservatively_flagged():
    # Documented limit, not a hole: a nested raise may or may not run, so the
    # handler counts as non-reraising. Lift the raise to the top level to clear it.
    h = _handler(
        "try:\n    f()\nexcept Exception as e:\n    if fatal(e):\n        raise\n    log.warning('x')\n"
    )
    assert cft._handler_kind(h) == "broad-except"


def test_broad_type_behind_a_name_alias_is_a_documented_evasion():
    # `_is_broad_type` resolves by name only; a module that rebinds Exception
    # is not detected. Pinned here so the docstring's coverage claim stays honest.
    h = _handler("try:\n    f()\nexcept E:\n    log.warning('x')\n")
    assert cft._handler_kind(h) is None
