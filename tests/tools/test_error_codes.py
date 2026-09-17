"""API error-code gate: every jsonify({"error": ...}) and abort(400+) under
src/quodeq/api must carry a machine-readable `code`.

No baseline: the ceiling is zero from day one.
"""
from __future__ import annotations

import ast

import check_error_codes as cec

_SAMPLE = '''\
def bare():
    return jsonify({"error": "x"}), 400


def gated():
    abort(404)


def coded():
    return jsonify({"error": "x", "code": "Y"})


def helper_response():
    return error_response("x", 400, "Y")
'''


def test_checker_finds_bare_jsonify_and_abort(tmp_path):
    module = tmp_path / "sample_routes.py"
    module.write_text(_SAMPLE, encoding="utf-8")
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    violations = cec._scan_tree(tree, "sample_routes.py")
    assert set(violations) == {
        ("sample_routes.py", 2, "uncoded-error"),
        ("sample_routes.py", 6, "abort"),
    }
    assert len(violations) == 2


def test_no_uncoded_error_responses() -> None:
    assert cec.collect_violations() == []
