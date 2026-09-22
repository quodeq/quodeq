"""Robustness of read_req_to_principle_map against malformed evaluator JSON.

The function contract is to degrade to an empty mapping on any unreadable or
malformed evaluator file (so callers stay permissive). Formerly the core-layer
_build_req_to_principle_map; the file read now lives in the data.fs adapter
and core receives it injected as ``req_map_reader``.
"""
from __future__ import annotations

import json

from quodeq.data.fs.standards_loader import read_req_to_principle_map


def test_list_top_level_json_returns_empty(tmp_path):
    (tmp_path / "security.json").write_text(json.dumps(["not", "a", "dict"]))
    assert read_req_to_principle_map(tmp_path, "security") == {}


def test_null_top_level_json_returns_empty(tmp_path):
    (tmp_path / "reliability.json").write_text("null")
    assert read_req_to_principle_map(tmp_path, "reliability") == {}


def test_non_dict_principle_items_do_not_crash(tmp_path):
    (tmp_path / "performance.json").write_text(
        json.dumps({"principles": ["garbage", 42, None]})
    )
    assert read_req_to_principle_map(tmp_path, "performance") == {}


def test_missing_file_returns_empty(tmp_path):
    assert read_req_to_principle_map(tmp_path, "usability") == {}


def test_well_formed_file_still_maps(tmp_path):
    (tmp_path / "usability.json").write_text(
        json.dumps({
            "principles": [
                {"name": "Learnability", "requirements": [{"id": "U-LRN-1"}]},
            ]
        })
    )
    assert read_req_to_principle_map(tmp_path, "usability") == {"U-LRN-1": "Learnability"}
