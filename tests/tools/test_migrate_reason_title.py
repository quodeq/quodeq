"""#683 — migrate_reason_title.migrate_entry must not raise on non-dict input."""
from __future__ import annotations

import pytest


class TestMigrateEntryNonDict:
    def test_list_input_returns_false(self) -> None:
        from migrate_reason_title import migrate_entry
        assert migrate_entry([{"reason": "x"}]) is False

    def test_string_input_returns_false(self) -> None:
        from migrate_reason_title import migrate_entry
        assert migrate_entry("just a string") is False

    def test_none_input_returns_false(self) -> None:
        from migrate_reason_title import migrate_entry
        assert migrate_entry(None) is False

    def test_int_input_returns_false(self) -> None:
        from migrate_reason_title import migrate_entry
        assert migrate_entry(42) is False

    def test_valid_dict_still_works(self) -> None:
        from migrate_reason_title import migrate_entry
        entry = {"reason": "Modularity -- separation of concerns", "principle": "Modularity"}
        # The function should handle a valid dict without raising
        result = migrate_entry(entry)
        assert isinstance(result, bool)
