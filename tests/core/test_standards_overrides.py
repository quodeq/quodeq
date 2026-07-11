import json

from quodeq.core.standards.overrides import (
    OVERRIDES_RELPATH,
    collect_declared_params,
    effective_params,
    load_project_overrides,
    resolve_requirement_text,
    validate_overrides,
)

REQ = {
    "id": "M-ANA-2",
    "text": "Functions MUST NOT exceed {max_lines} lines",
    "params": {
        "max_lines": {"label": "Max function lines", "type": "int",
                      "default": 50, "min": 10, "max": 500},
    },
}


def _write_overrides(root, overrides):
    path = root / OVERRIDES_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "overrides": overrides}))


def test_resolve_text_uses_default_without_override():
    assert resolve_requirement_text(REQ) == "Functions MUST NOT exceed 50 lines"


def test_resolve_text_applies_valid_override():
    assert resolve_requirement_text(REQ, {"max_lines": 60}) == (
        "Functions MUST NOT exceed 60 lines")


def test_resolve_text_ignores_out_of_bounds_override():
    assert resolve_requirement_text(REQ, {"max_lines": 9999}) == (
        "Functions MUST NOT exceed 50 lines")


def test_resolve_text_ignores_wrong_type_override():
    assert resolve_requirement_text(REQ, {"max_lines": "sixty"}) == (
        "Functions MUST NOT exceed 50 lines")
    assert resolve_requirement_text(REQ, {"max_lines": True}) == (
        "Functions MUST NOT exceed 50 lines")


def test_resolve_text_without_params_returns_text_verbatim():
    req = {"id": "M-MOD-2", "text": "Modules MUST be cohesive"}
    assert resolve_requirement_text(req, {"max_lines": 60}) == "Modules MUST be cohesive"


def test_resolve_text_leaves_unknown_placeholder_untouched():
    req = dict(REQ, text="Limit is {max_lines} and {mystery}")
    assert resolve_requirement_text(req) == "Limit is 50 and {mystery}"


def test_effective_params_merges_override_and_default():
    req = dict(REQ)
    req["params"] = dict(REQ["params"], max_depth={
        "label": "Max nesting depth", "type": "int",
        "default": 4, "min": 1, "max": 20})
    values = effective_params(req, {"max_depth": 6})
    assert values == {"max_lines": 50, "max_depth": 6}


def test_load_project_overrides_missing_file_returns_empty(tmp_path):
    assert load_project_overrides(tmp_path) == {}
    assert load_project_overrides(None) == {}


def test_load_project_overrides_reads_file(tmp_path):
    _write_overrides(tmp_path, {"M-ANA-2": {"max_lines": 60}})
    assert load_project_overrides(tmp_path) == {"M-ANA-2": {"max_lines": 60}}


def test_load_project_overrides_malformed_returns_empty(tmp_path):
    path = tmp_path / OVERRIDES_RELPATH
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert load_project_overrides(tmp_path) == {}


def test_load_project_overrides_drops_non_dict_entries(tmp_path):
    _write_overrides(tmp_path, {"M-ANA-2": {"max_lines": 60}, "M-MOD-4": 12})
    assert load_project_overrides(tmp_path) == {"M-ANA-2": {"max_lines": 60}}


def test_collect_declared_params(tmp_path):
    (tmp_path / "maintainability.json").write_text(json.dumps({
        "id": "maintainability",
        "principles": [{"name": "Analyzability", "requirements": [REQ]}],
    }))
    (tmp_path / "security.json").write_text(json.dumps({
        "id": "security",
        "principles": [{"name": "Confidentiality", "requirements": [
            {"id": "S-CO-1", "text": "Secrets MUST NOT be committed"}]}],
    }))
    declared = collect_declared_params(tmp_path)
    assert set(declared) == {"M-ANA-2"}
    assert declared["M-ANA-2"]["max_lines"]["default"] == 50


def test_validate_overrides_accepts_valid_document():
    declared = {"M-ANA-2": REQ["params"]}
    clean, errors = validate_overrides({"M-ANA-2": {"max_lines": 60}}, declared)
    assert clean == {"M-ANA-2": {"max_lines": 60}}
    assert errors == []


def test_validate_overrides_reports_field_errors():
    declared = {"M-ANA-2": REQ["params"]}
    clean, errors = validate_overrides(
        {"M-ANA-2": {"max_lines": 9999, "nope": 1}, "X-XX-9": {"a": 1}},
        declared)
    assert clean == {}
    assert len(errors) == 3


def test_validate_overrides_rejects_non_dict():
    clean, errors = validate_overrides(["nope"], {})
    assert clean == {}
    assert errors == ["overrides must be an object"]


def test_extract_requirements_applies_overrides():
    from quodeq.core.standards.refs import extract_requirements
    data = {"principles": [{"name": "Analyzability", "requirements": [REQ]}]}
    plain = extract_requirements(data)
    tuned = extract_requirements(data, overrides={"M-ANA-2": {"max_lines": 60}})
    assert plain["M-ANA-2"]["text"] == "Functions MUST NOT exceed 50 lines"
    assert tuned["M-ANA-2"]["text"] == "Functions MUST NOT exceed 60 lines"
