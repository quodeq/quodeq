"""When the deleted store is rewritten.

delete_finding writes only when the key is new; delete_all_dismissed writes
the store whenever it has dismissed entries to convert, even if every key is
already there.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from quodeq.services.deleted import delete_all_dismissed, delete_finding, load_deleted

_WRITE_TARGET = "quodeq.services.deleted.write_deleted_entries"
_FINDING = {"req": "M-1", "file": "a.py", "line": 3, "dimension": "maint", "principle": "Modularity"}


def test_delete_finding_writes_a_new_key_once(tmp_path):
    delete_finding(tmp_path, dict(_FINDING))
    with patch(_WRITE_TARGET) as write:
        delete_finding(tmp_path, dict(_FINDING))
    write.assert_not_called()
    assert len(load_deleted(tmp_path)) == 1


def test_delete_all_dismissed_writes_even_when_every_key_exists(tmp_path):
    delete_finding(tmp_path, dict(_FINDING))
    dismissed = [{**_FINDING, "fingerprint": None}]
    with patch("quodeq.services.deleted.load_dismissed", return_value=dismissed), \
            patch(_WRITE_TARGET) as write:
        assert delete_all_dismissed(tmp_path, writer=MagicMock()) == 1
    write.assert_called_once()
    assert write.call_args.args[1] == load_deleted(tmp_path)
