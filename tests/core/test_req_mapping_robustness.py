"""Robustness of _build_req_to_principle_map against malformed evaluator JSON.

The function contract is to degrade to an empty mapping on any unreadable or
malformed evaluator file (so callers stay permissive), but its except clause
only caught OSError/ValueError. A top-level JSON value that is valid but not a
dict (a list, or null) made data.get(...) raise AttributeError and crash.
"""
from __future__ import annotations

import json

from quodeq.core.evidence._req_mapping import _build_req_to_principle_map


def test_list_top_level_json_returns_empty(tmp_path):
    (tmp_path / "security.json").write_text(json.dumps(["not", "a", "dict"]))
    assert _build_req_to_principle_map("security", tmp_path) == {}


def test_null_top_level_json_returns_empty(tmp_path):
    (tmp_path / "reliability.json").write_text("null")
    assert _build_req_to_principle_map("reliability", tmp_path) == {}


def test_non_dict_principle_items_do_not_crash(tmp_path):
    (tmp_path / "performance.json").write_text(
        json.dumps({"principles": ["garbage", 42, None]})
    )
    assert _build_req_to_principle_map("performance", tmp_path) == {}


def test_well_formed_file_still_maps(tmp_path):
    (tmp_path / "usability.json").write_text(
        json.dumps({
            "principles": [
                {"name": "Learnability", "requirements": [{"id": "U-LRN-1"}]},
            ]
        })
    )
    assert _build_req_to_principle_map("usability", tmp_path) == {"U-LRN-1": "Learnability"}
