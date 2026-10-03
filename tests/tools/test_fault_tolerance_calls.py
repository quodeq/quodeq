"""Unit tests for the call-site rules check_fault_tolerance.py runs per module."""
import ast

import check_fault_tolerance as cft


def _kinds(src: str) -> list[str]:
    return [k for _, _, k in cft._scan_tree(ast.parse(src), "m.py")]


def test_int_in_try_catching_type_and_value_errors_is_flagged():
    src = "try:\n    n = int(v)\nexcept (TypeError, ValueError):\n    n = 0\n"
    assert _kinds(src) == ["int-overflow"]


def test_int_in_try_catching_valueerror_alone_is_clean():
    src = "try:\n    n = int(v)\nexcept ValueError:\n    n = 0\n"
    assert _kinds(src) == []


def test_int_in_try_with_separate_value_and_type_handlers_is_flagged():
    src = "try:\n    n = int(v)\nexcept ValueError:\n    n = 0\nexcept TypeError:\n    n = 1\n"
    assert _kinds(src) == ["int-overflow"]


def test_int_in_try_catching_exception_is_clean():
    src = "try:\n    n = int(v)\nexcept Exception:\n    raise\n"
    assert _kinds(src) == []


def test_int_in_try_catching_overflow_is_clean():
    src = "try:\n    n = int(v)\nexcept (TypeError, ValueError, OverflowError):\n    n = 0\n"
    assert _kinds(src) == []


def test_int_in_try_with_separate_arithmetic_handler_is_clean():
    src = "try:\n    n = int(v)\nexcept (TypeError, ValueError):\n    n = 0\nexcept ArithmeticError:\n    n = 1\n"
    assert _kinds(src) == []


def test_int_in_try_without_valueerror_handler_is_clean():
    src = "try:\n    n = int(v)\nexcept KeyError:\n    n = 0\n"
    assert _kinds(src) == []


def test_int_inside_nested_function_in_try_is_clean():
    src = "try:\n    def f():\n        return int(v)\nexcept (TypeError, ValueError):\n    pass\n"
    assert "int-overflow" not in _kinds(src)


def test_int_outside_try_is_clean():
    assert _kinds("n = int(v)\n") == []


def test_only_innermost_try_counts():
    src = (
        "try:\n"
        "    try:\n"
        "        n = int(v)\n"
        "    except KeyError:\n"
        "        n = 0\n"
        "except (TypeError, ValueError):\n"
        "    n = 1\n"
    )
    assert _kinds(src) == []


def test_int_in_handler_body_is_not_guarded_by_that_try():
    src = "try:\n    f()\nexcept (TypeError, ValueError):\n    n = int(v)\n"
    assert _kinds(src) == []


def test_flagged_call_keys_at_its_own_line():
    src = "try:\n    f()\n    n = int(v)\nexcept (TypeError, ValueError):\n    n = 0\n"
    assert cft._scan_tree(ast.parse(src), "m.py") == [("m.py", 3, "int-overflow")]


def test_int_in_bare_except_try_is_not_int_overflow():
    src = "try:\n    n = int(v)\nexcept:\n    n = 0\n"
    assert _kinds(src) == ["bare-except"]


def test_int_in_trystar_is_treated_like_try():
    src = "try:\n    n = int(v)\nexcept* (TypeError, ValueError):\n    n = 0\n"
    assert _kinds(src) == ["int-overflow"]


def test_mkstemp_before_oserror_try_is_flagged():
    src = ("fd, name = tempfile.mkstemp()\ntry:\n    write(fd)\n"
           "except OSError:\n    log()\n")
    assert _kinds(src) == ["mkstemp-before-try"]


def test_mkstemp_inside_try_is_clean():
    src = ("try:\n    fd, name = tempfile.mkstemp()\n    write(fd)\n"
           "except OSError:\n    log()\n")
    assert _kinds(src) == []


def test_mkstemp_before_try_without_oserror_handler_is_clean():
    src = "fd, name = tempfile.mkstemp()\ntry:\n    write(fd)\nexcept ValueError:\n    log()\n"
    assert _kinds(src) == []


def test_bare_mkstemp_before_try_catching_a_tuple_with_ioerror_is_flagged():
    src = "pair: tuple = mkstemp()\ntry:\n    write(pair)\nexcept (ValueError, IOError):\n    log()\n"
    assert _kinds(src) == ["mkstemp-before-try"]


def test_mkstemp_before_bare_except_try_is_flagged():
    src = "fd, name = tempfile.mkstemp()\ntry:\n    write(fd)\nexcept:\n    raise\n"
    assert "mkstemp-before-try" in _kinds(src)


def test_mkstemp_with_no_following_try_is_clean():
    src = "fd, name = tempfile.mkstemp()\nwrite(fd)\ntry:\n    f()\nexcept OSError:\n    log()\n"
    assert _kinds(src) == []


def test_mkstemp_before_try_in_a_function_keys_at_the_mkstemp_line():
    src = ("def save():\n    x = 1\n    fd, name = tempfile.mkstemp()\n    try:\n        write(fd)\n"
           "    except Exception:\n        raise\n")
    assert cft._scan_tree(ast.parse(src), "m.py") == [("m.py", 3, "mkstemp-before-try")]
