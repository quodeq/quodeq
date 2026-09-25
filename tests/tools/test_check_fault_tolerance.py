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


def _kinds_with_lines(src: str) -> list[tuple[int, str]]:
    """Scan a source snippet the way the ratchet scans a file; return (lineno, kind)."""
    return [(lineno, kind) for _rel, lineno, kind in cft._scan_tree(ast.parse(src), "x.py")]


def test_contextlib_suppress_is_flagged():
    assert _kinds_with_lines("with contextlib.suppress(OSError):\n    f()\n") == [(1, "suppress")]


def test_bare_suppress_is_flagged():
    assert _kinds_with_lines("with suppress(OSError):\n    f()\n") == [(1, "suppress")]


def test_plain_open_is_not_flagged():
    assert _kinds_with_lines("with open('x') as fh:\n    f(fh)\n") == []


def test_async_with_suppress_is_flagged():
    src = "async def g():\n    async with contextlib.suppress(OSError):\n        await f()\n"
    assert _kinds_with_lines(src) == [(2, "suppress")]


def test_aliased_module_suppress_is_flagged():
    # Any `X.suppress(...)`, since contextlib can be imported under an alias.
    assert _kinds_with_lines("with cl.suppress(OSError):\n    f()\n") == [(1, "suppress")]


# suppress() is flagged wherever it is CALLED, not only as
# a direct `with` item, so the two evasions the review probed are closed.

def test_suppress_via_exit_stack_is_flagged():
    src = "with ExitStack() as stack:\n    stack.enter_context(contextlib.suppress(OSError))\n    f()\n"
    assert _kinds_with_lines(src) == [(2, "suppress")]


def test_suppress_bound_to_a_name_first_is_flagged():
    src = "cm = contextlib.suppress(OSError)\nwith cm:\n    f()\n"
    assert _kinds_with_lines(src) == [(1, "suppress")]


def test_suppress_is_keyed_once_per_call_site():
    # The `with` line and the call are the same line; one entry, not two.
    src = "with contextlib.suppress(OSError), open('x') as fh:\n    f(fh)\n"
    assert _kinds_with_lines(src) == [(1, "suppress")]


# `_reraises` is a reachability-aware scan of the handler's
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


def _kinds(src: str, rel: str = "src/quodeq/x.py") -> list[str]:
    return [kind for _, _, kind in cft._scan_tree(ast.parse(src), rel)]


_HELPER = (
    "def run_isolated(fn, *, label, log, on_error=None):\n"
    "    try:\n"
    "        return fn()\n"
    "    except Exception as exc:\n"
    "        log.warning(label)\n"
    "        return None\n"
)


def test_the_helper_own_broad_catch_is_allowed():
    assert _kinds(_HELPER, rel="src/quodeq/shared/fault_isolation.py") == []


def test_the_same_catch_elsewhere_is_still_flagged():
    assert _kinds(_HELPER, rel="src/quodeq/other.py") == ["broad-except"]


def test_call_as_a_loop_body_statement_is_allowed():
    src = "for item in items:\n    run_isolated(lambda: work(item), label='x', log=log)\n"
    assert _kinds(src) == []


def test_call_as_the_whole_function_body_is_allowed():
    src = "def _run(self):\n    '''Thread target.'''\n    return run_isolated(self._work, label='x', log=self._log)\n"
    assert _kinds(src) == []


def test_call_in_a_lambda_passed_as_a_callback_is_allowed():
    src = "threading.Thread(target=lambda: run_isolated(work, label='x', log=log)).start()\n"
    assert _kinds(src) == []


def test_call_mid_function_is_flagged():
    src = "def f():\n    prepare()\n    run_isolated(work, label='x', log=log)\n    finish()\n"
    assert _kinds(src) == ["isolated-call"]


def test_call_nested_in_an_if_inside_a_loop_is_flagged():
    src = "for item in items:\n    if item:\n        run_isolated(work, label='x', log=log)\n"
    assert _kinds(src) == ["isolated-call"]


def test_attribute_spelling_is_checked_too():
    src = "def f():\n    a()\n    fault_isolation.run_isolated(work, label='x', log=log)\n"
    assert _kinds(src) == ["isolated-call"]
