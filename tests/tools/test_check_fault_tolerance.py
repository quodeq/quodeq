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
