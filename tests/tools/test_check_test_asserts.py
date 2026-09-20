"""Unit tests and gate for tools/check_test_asserts.py: assertions per test."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import _test_asserts_rules as rules
import check_test_asserts

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _py(body: str) -> str:
    return "def test_x():\n" + "".join(f"    {line}\n" for line in body.splitlines())


def _asserts(count: int) -> str:
    return "\n".join(f"assert {i} == {i}" for i in range(count))


def test_python_test_with_nine_asserts_is_flagged():
    (case,) = rules.python_tests(_py(_asserts(9)), "tests/test_a.py")
    assert (case.key, case.count) == ("tests/test_a.py:test_x", 9)
    assert rules.over_limit([case]) == [case]


def test_python_test_with_eight_asserts_is_not_flagged():
    (case,) = rules.python_tests(_py(_asserts(8)), "tests/test_a.py")
    assert case.count == 8
    assert rules.over_limit([case]) == []


def test_pytest_raises_block_counts_as_one_assertion():
    source = _py("with pytest.raises(ValueError):\n    f()")
    (case,) = rules.python_tests(source, "tests/test_a.py")
    assert case.count == 1


def test_pytest_raises_counts_once_even_with_an_assert_inside():
    source = _py("with pytest.raises(ValueError) as e:\n    f()\nassert 'x' in str(e)")
    (case,) = rules.python_tests(source, "tests/test_a.py")
    assert case.count == 2


def test_helper_functions_and_non_test_functions_are_ignored():
    source = "def helper():\n    assert 1\n\n\ndef test_x():\n    assert 2\n"
    assert [c.key for c in rules.python_tests(source, "tests/test_a.py")] == ["tests/test_a.py:test_x"]


def test_test_methods_are_keyed_with_their_class():
    source = "class TestThing:\n    def test_x(self):\n        assert 1\n"
    (case,) = rules.python_tests(source, "tests/test_a.py")
    assert case.key == "tests/test_a.py:TestThing.test_x"


def test_async_test_functions_are_counted():
    source = "async def test_x():\n    assert 1\n    assert 2\n"
    (case,) = rules.python_tests(source, "tests/test_a.py")
    assert case.count == 2


def test_python_syntax_error_yields_no_tests(capsys):
    assert rules.python_tests("def (:\n", "tests/test_a.py") == []
    assert "skipping" in capsys.readouterr().err


def _js_it(count: int, name: str = "does a thing", caller: str = "it") -> str:
    body = "\n".join(f"  expect({i}).toBe({i});" for i in range(count))
    return f"{caller}('{name}', () => {{\n{body}\n}});\n"


def test_js_test_with_nine_expects_is_flagged():
    (case,) = rules.js_tests(_js_it(9), "src/a.test.jsx")
    assert (case.key, case.count) == ("src/a.test.jsx:does a thing", 9)
    assert rules.over_limit([case]) == [case]


def test_js_test_with_eight_expects_is_not_flagged():
    (case,) = rules.js_tests(_js_it(8), "src/a.test.jsx")
    assert rules.over_limit([case]) == []


def test_js_test_alias_and_modifier_are_recognised():
    names = {c.key for c in rules.js_tests(_js_it(1, "a", "test") + _js_it(1, "b", "it.only"), "x.test.js")}
    assert names == {"x.test.js:a", "x.test.js:b"}


def test_js_expects_are_scoped_to_their_own_test():
    source = _js_it(2, "first") + _js_it(3, "second")
    assert [(c.name, c.count) for c in rules.js_tests(source, "x.test.js")] == [
        ("first", 2), ("second", 3),
    ]


def test_js_tests_inside_a_describe_are_found():
    source = "describe('group', () => {\n" + _js_it(2, "inner") + "});\n"
    (case,) = rules.js_tests(source, "x.test.js")
    assert (case.name, case.count) == ("inner", 2)


def test_js_expects_in_strings_and_comments_are_not_counted():
    source = (
        "it('quoted', () => {\n"
        "  // expect(1).toBe(1);\n"
        "  /* expect(2).toBe(2); */\n"
        "  const s = 'expect(3)';\n"
        "  const t = `expect(4)`;\n"
        "  expect(5).toBe(5);\n"
        "});\n"
    )
    (case,) = rules.js_tests(source, "x.test.js")
    assert case.count == 1


def test_js_test_name_from_a_template_literal():
    source = "it(`templated`, () => {\n  expect(1).toBe(1);\n});\n"
    (case,) = rules.js_tests(source, "x.test.js")
    assert case.name == "templated"


def test_js_braces_in_strings_do_not_end_the_body():
    source = "it('a', () => {\n  const s = '})';\n  expect(1).toBe(1);\n});\nit('b', () => {\n});\n"
    assert [(c.name, c.count) for c in rules.js_tests(source, "x.test.js")] == [("a", 1), ("b", 0)]


def test_scan_reads_python_and_js_trees(tmp_path):
    py = tmp_path / "tests" / "test_a.py"
    py.parent.mkdir(parents=True)
    py.write_text(_py(_asserts(9)), encoding="utf-8")
    js = tmp_path / "src" / "quodeq" / "ui" / "src" / "a.test.jsx"
    js.parent.mkdir(parents=True)
    js.write_text(_js_it(9), encoding="utf-8")

    keys = [c.key for c in rules.scan_tree(tmp_path)]
    assert keys == ["src/quodeq/ui/src/a.test.jsx:does a thing", "tests/test_a.py:test_x"]


def test_new_violation_outside_the_baseline_fails_the_gate(tmp_path, monkeypatch, capsys):
    (case,) = rules.python_tests(_py(_asserts(9)), "tests/test_a.py")
    baseline = tmp_path / "test_asserts_baseline.txt"
    baseline.write_text("# header\n", encoding="utf-8")
    monkeypatch.setattr(check_test_asserts, "BASELINE_PATH", baseline)
    monkeypatch.setattr(check_test_asserts, "_scan", lambda: [case])

    assert check_test_asserts.main([]) == 1
    assert "tests/test_a.py:test_x" in capsys.readouterr().out


def test_baselined_violation_passes_the_gate(tmp_path, monkeypatch):
    (case,) = rules.python_tests(_py(_asserts(9)), "tests/test_a.py")
    baseline = tmp_path / "test_asserts_baseline.txt"
    monkeypatch.setattr(check_test_asserts, "BASELINE_PATH", baseline)
    monkeypatch.setattr(check_test_asserts, "_scan", lambda: [case])

    assert check_test_asserts.main(["--update-baseline"]) == 0
    assert check_test_asserts.load_baseline(baseline) == {"tests/test_a.py:test_x"}
    assert check_test_asserts.main([]) == 0


def test_describe_reports_the_assertion_count():
    (case,) = rules.python_tests(_py(_asserts(9)), "tests/test_a.py")
    assert "9 assertion" in check_test_asserts.describe(case)


def test_unknown_argument_is_rejected():
    assert check_test_asserts.main(["--nope"]) == 2


def test_gate_passes_on_current_tree():
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "check_test_asserts.py")],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# Revise DOWNWARD as over-asserting tests are split; the target is 0.
# NEVER raise without a justification reviewed in the PR that raises it.
BASELINE_CEILING = 250


def test_baseline_only_shrinks():
    count = len(check_test_asserts.load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). "
        "Split the test instead of grandfathering more assertions in one test."
    )
