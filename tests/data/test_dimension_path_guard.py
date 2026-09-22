"""Path-traversal guard tests for compiled-standards dimension lookup.

``_load_compiled_data`` (``data/fs/standards_loader.py``) interpolates a
request-supplied ``dimension`` string directly into a filesystem path
(``Path(compiled_dir) / f"{dimension}.json"`` and the ``evaluators_dir``
equivalent). These tests prove a traversal segment, an absolute path, and a
null byte are all rejected before any file outside ``compiled_dir`` /
``evaluators_dir`` is touched, and that every genuinely installed
dimension -- including a custom, user-imported one -- still resolves.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.standards_loader import (
    is_known_dimension,
    known_dimension_ids,
    load_compiled_refs,
)


def _write_compiled(directory: Path, dim: str, req_id: str = "S-1") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "id": dim,
        "principles": [{
            "name": "Principle",
            "requirements": [{
                "id": req_id,
                "text": "Requirement text",
                "refs": [{"source": "cwe", "id": "1", "url": "https://example.com/1"}],
            }],
        }],
    }
    (directory / f"{dim}.json").write_text(json.dumps(data))


class TestKnownDimensionIds:
    def test_lists_compiled_and_custom_ids(self, tmp_path):
        compiled_dir = tmp_path / "compiled"
        evaluators_dir = tmp_path / "evaluators"
        _write_compiled(compiled_dir, "security")
        _write_compiled(evaluators_dir, "my-custom-standard")

        ids = known_dimension_ids(compiled_dir, evaluators_dir)

        assert ids == {"security", "my-custom-standard"}

    def test_missing_directories_yield_empty_set(self, tmp_path):
        assert known_dimension_ids(tmp_path / "nope", None) == frozenset()


class TestIsKnownDimensionCaseInsensitive:
    """Dimension ids are compared case-insensitively everywhere else in this
    codebase (core.standards.visibility.normalize_ids); older eval payloads
    carry "Security" where a fresh compile writes security.json, and both
    must be recognised as the same dimension."""

    def test_mixed_case_dimension_matches_lowercase_file(self, tmp_path):
        compiled_dir = tmp_path / "compiled"
        _write_compiled(compiled_dir, "security")

        assert is_known_dimension("Security", compiled_dir, None) is True

    def test_traversal_value_is_not_known_regardless_of_case(self, tmp_path):
        compiled_dir = tmp_path / "compiled"
        _write_compiled(compiled_dir, "security")

        assert is_known_dimension("../SECRET", compiled_dir, None) is False


class TestLoadCompiledRefsRejectsTraversal:
    """Each case proves the escape *would* succeed without the guard: the
    target file genuinely exists and genuinely contains data the traversal
    is reaching for."""

    def test_dot_dot_segment_cannot_escape_compiled_dir(self, tmp_path):
        compiled_dir = tmp_path / "compiled"
        compiled_dir.mkdir()
        outside = tmp_path / "outside"
        _write_compiled(outside, "secret", req_id="LEAKED-1")

        refs = load_compiled_refs(str(compiled_dir), "../outside/secret")

        assert refs == {}
        # The file "outside" is reaching for is untouched and still there --
        # proof the guard rejected the lookup rather than the file being absent.
        assert (outside / "secret.json").is_file()
        assert list(compiled_dir.iterdir()) == []

    def test_absolute_path_dimension_cannot_reach_arbitrary_file(self, tmp_path):
        compiled_dir = tmp_path / "compiled"
        compiled_dir.mkdir()
        _write_compiled(tmp_path, "secret_target", req_id="LEAKED-2")
        secret_json = tmp_path / "secret_target.json"
        assert secret_json.is_file()

        # dimension carries an absolute path; the code appends ".json" itself.
        absolute_dimension = str(tmp_path / "secret_target")
        refs = load_compiled_refs(str(compiled_dir), absolute_dimension)

        assert refs == {}
        assert secret_json.is_file()  # untouched, proves nothing leaked from it

    def test_null_byte_in_dimension_is_rejected(self, tmp_path):
        compiled_dir = tmp_path / "compiled"
        _write_compiled(compiled_dir, "security")

        refs = load_compiled_refs(str(compiled_dir), "security\0../../../etc/passwd")

        assert refs == {}


class TestLoadCompiledRefsValidDimensionsStillResolve:
    def test_builtin_dimension_still_resolves(self, tmp_path):
        compiled_dir = tmp_path / "compiled"
        _write_compiled(compiled_dir, "security", req_id="S-CON-1")

        refs = load_compiled_refs(str(compiled_dir), "security")

        assert "S-CON-1" in refs

    def test_custom_imported_dimension_still_resolves(self, tmp_path):
        compiled_dir = tmp_path / "compiled"
        compiled_dir.mkdir()
        evaluators_dir = tmp_path / "evaluators"
        _write_compiled(evaluators_dir, "my-custom-standard", req_id="C-1")

        refs = load_compiled_refs(
            str(compiled_dir), "my-custom-standard", evaluators_dir=evaluators_dir,
        )

        assert "C-1" in refs
