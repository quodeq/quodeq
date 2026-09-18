"""API error-code gate: every error response under src/quodeq/api must carry
a machine-readable `code`, whether it is built with jsonify(), returned as a
(dict, status) tuple, or raised with abort(400+).

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

# One function per shape the checker learned in final-review item 9.
_TUPLE_SAMPLE = '''\
import http
from http import HTTPStatus


def bare_dict_tuple():
    return {"error": "x"}, 400


def bare_dict_tuple_httpstatus():
    return {"error": "x"}, HTTPStatus.BAD_REQUEST


def bare_dict_tuple_qualified_httpstatus():
    return {"error": "x"}, http.HTTPStatus.NOT_FOUND


def bare_jsonify_qualified_httpstatus():
    return jsonify({"error": "x"}), http.HTTPStatus.CONFLICT


def coded_dict_tuple():
    return {"error": "x", "code": "Y"}, 400


def reserved_error_slot():
    return {"error": None, "ok": True}


def reserved_error_slot_in_a_tuple():
    return {"error": None, "ok": True}, 400


def success_tuple():
    return {"error": "x"}, 200


def abort_with_a_variable_status():
    abort(status)


def reserved_error_slot_jsonified():
    return jsonify({"error": None, "ok": True})
'''


def _scan(tmp_path, source: str) -> set[tuple[str, int, str]]:
    module = tmp_path / "sample_routes.py"
    module.write_text(source, encoding="utf-8")
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    return set(cec._scan_tree(tree, "sample_routes.py"))


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


def test_checker_finds_uncoded_dict_return_tuples(tmp_path):
    """A (dict, status) return is the same error response without jsonify,
    and HTTPStatus counts whether it is imported bare or as http.HTTPStatus."""
    assert _scan(tmp_path, _TUPLE_SAMPLE) == {
        ("sample_routes.py", 6, "uncoded-error"),
        ("sample_routes.py", 10, "uncoded-error"),
        ("sample_routes.py", 14, "uncoded-error"),
        ("sample_routes.py", 18, "uncoded-error"),
    }


def test_no_uncoded_error_responses() -> None:
    assert cec.collect_violations() == []
