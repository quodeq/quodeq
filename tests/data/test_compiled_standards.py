"""Compiled-standards directory reads belong to the data layer.

api/standards_overrides_routes globbed the compiled dir and json-parsed
each file inline; the route now keeps only its mapping logic.
"""
from __future__ import annotations

import json


def _write(d, name: str, payload) -> None:
    (d / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


class TestIterCompiledStandards:
    def test_yields_parsed_payloads_sorted(self, tmp_path):
        from quodeq.data.fs.compiled_standards import iter_compiled_standards

        _write(tmp_path, "b-std", {"id": "b-std"})
        _write(tmp_path, "a-std", {"id": "a-std"})

        out = list(iter_compiled_standards(tmp_path))

        assert [stem for stem, _ in out] == ["a-std", "b-std"]
        assert [data["id"] for _, data in out] == ["a-std", "b-std"]

    def test_skips_unreadable_and_non_object_files(self, tmp_path):
        from quodeq.data.fs.compiled_standards import iter_compiled_standards

        _write(tmp_path, "good", {"id": "good"})
        (tmp_path / "broken.json").write_text("{nope", encoding="utf-8")
        (tmp_path / "list.json").write_text("[1, 2]", encoding="utf-8")

        assert [stem for stem, _ in iter_compiled_standards(tmp_path)] == ["good"]

    def test_skips_a_deeply_nested_file(self, tmp_path, deeply_nested_json):
        """A hand-edited standard must never 500 a request, RecursionError
        included: the C JSON decoder overflows its call stack on deeply nested
        input and raises a RuntimeError subclass, which the narrow
        (OSError, ValueError, UnicodeDecodeError) catch let escape."""
        from quodeq.data.fs.compiled_standards import iter_compiled_standards

        _write(tmp_path, "good", {"id": "good"})
        (tmp_path / "nested.json").write_text(deeply_nested_json, encoding="utf-8")

        assert [stem for stem, _ in iter_compiled_standards(tmp_path)] == ["good"]

    def test_missing_dir_yields_nothing(self, tmp_path):
        from quodeq.data.fs.compiled_standards import iter_compiled_standards

        assert list(iter_compiled_standards(tmp_path / "nope")) == []


class TestRouteDelegation:
    def test_counts_uses_the_adapter(self, tmp_path):
        from quodeq.services.standards_overrides import override_counts_by_dimension

        _write(tmp_path, "sec", {
            "id": "sec",
            "principles": [{"requirements": [{"id": "S-1"}, {"id": "S-2"}]}],
        })

        counts = override_counts_by_dimension({"S-1": {}, "S-2": {}, "OTHER": {}}, tmp_path)

        assert counts == {"sec": 2}

    def test_api_module_does_no_filesystem_parsing(self):
        """The route module must not glob or json-parse the compiled dir."""
        from quodeq.api import standards_overrides_routes as routes

        src = open(routes.__file__).read()
        assert ".glob(" not in src
        assert "read_text(" not in src


class TestProjectOverridesWriter:
    def test_save_then_load_round_trip(self, tmp_path):
        from quodeq.data.fs.standards_prefs import (
            load_project_overrides, save_project_overrides,
        )

        save_project_overrides(tmp_path, {"S-1": {"floorMajor": 5.0}})

        assert load_project_overrides(tmp_path) == {"S-1": {"floorMajor": 5.0}}

    def test_clear_removes_the_file(self, tmp_path):
        from quodeq.data.fs.standards_prefs import (
            clear_project_overrides, load_project_overrides, save_project_overrides,
        )

        save_project_overrides(tmp_path, {"S-1": {"floorMajor": 5.0}})
        clear_project_overrides(tmp_path)

        assert load_project_overrides(tmp_path) == {}

    def test_clear_is_idempotent(self, tmp_path):
        from quodeq.data.fs.standards_prefs import clear_project_overrides

        clear_project_overrides(tmp_path)  # must not raise


def test_overrides_route_does_no_filesystem_writes():
    from quodeq.api import standards_overrides_routes as routes

    src = open(routes.__file__).read()
    assert "write_text(" not in src
    assert "unlink(" not in src
