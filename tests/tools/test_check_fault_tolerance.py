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


def _with_node(src: str) -> ast.With | ast.AsyncWith:
    """Parse a one-statement `with`/`async with` snippet and return its node."""
    tree = ast.parse(src)
    node = tree.body[0]
    if isinstance(node, ast.AsyncFunctionDef):
        node = node.body[0]
    assert isinstance(node, (ast.With, ast.AsyncWith))
    return node


def test_contextlib_suppress_is_flagged():
    node = _with_node("with contextlib.suppress(OSError):\n    f()\n")
    assert cft._with_has_suppress(node) is True


def test_bare_suppress_is_flagged():
    node = _with_node("with suppress(OSError):\n    f()\n")
    assert cft._with_has_suppress(node) is True


def test_plain_open_is_not_flagged():
    node = _with_node("with open('x') as fh:\n    f(fh)\n")
    assert cft._with_has_suppress(node) is False


def test_async_with_suppress_is_flagged():
    node = _with_node(
        "async def g():\n    async with contextlib.suppress(OSError):\n        await f()\n"
    )
    assert cft._with_has_suppress(node) is True


def test_aliased_module_suppress_is_flagged():
    # Any `X.suppress(...)`, since contextlib can be imported under an alias.
    node = _with_node("with cl.suppress(OSError):\n    f()\n")
    assert cft._with_has_suppress(node) is True
