"""Per-project JSON artifacts (repository_info.json, scan.json) are owned
by the data layer; services delegate instead of calling write_text/read_text.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from quodeq.core.types.scan import ScanData


class TestReadRepositoryInfo:
    def test_missing_returns_none(self, tmp_path):
        from quodeq.data.fs.project_files import read_repository_info

        assert read_repository_info(tmp_path) is None

    def test_corrupt_returns_none(self, tmp_path):
        from quodeq.data.fs.project_files import read_repository_info

        (tmp_path / "repository_info.json").write_text("{nope")
        assert read_repository_info(tmp_path) is None

    def test_non_dict_json_returns_none(self, tmp_path):
        from quodeq.data.fs.project_files import read_repository_info

        (tmp_path / "repository_info.json").write_text("[1, 2]")
        assert read_repository_info(tmp_path) is None

    def test_valid_returns_dict(self, tmp_path):
        from quodeq.data.fs.project_files import read_repository_info

        (tmp_path / "repository_info.json").write_text('{"path": "/x"}')
        assert read_repository_info(tmp_path) == {"path": "/x"}


class TestRepositoryInfoExists:
    def test_absent_returns_false(self, tmp_path):
        from quodeq.data.fs.project_files import repository_info_exists

        assert repository_info_exists(tmp_path) is False

    def test_present_even_corrupt_returns_true(self, tmp_path):
        from quodeq.data.fs.project_files import repository_info_exists

        (tmp_path / "repository_info.json").write_text("{nope")
        assert repository_info_exists(tmp_path) is True


class TestReadScanTotalFiles:
    def test_reads_total_files(self, tmp_path):
        from quodeq.data.fs.project_files import read_scan_total_files

        (tmp_path / "scan.json").write_text(json.dumps({"total_files": 1855}))
        assert read_scan_total_files(tmp_path) == 1855

    def test_zero_when_missing(self, tmp_path):
        from quodeq.data.fs.project_files import read_scan_total_files

        assert read_scan_total_files(tmp_path) == 0

    def test_zero_when_corrupt(self, tmp_path):
        from quodeq.data.fs.project_files import read_scan_total_files

        (tmp_path / "scan.json").write_text("{nope")
        assert read_scan_total_files(tmp_path) == 0

    def test_zero_when_not_int(self, tmp_path):
        from quodeq.data.fs.project_files import read_scan_total_files

        (tmp_path / "scan.json").write_text(json.dumps({"total_files": "many"}))
        assert read_scan_total_files(tmp_path) == 0

    def test_zero_when_non_dict_json(self, tmp_path):
        from quodeq.data.fs.project_files import read_scan_total_files

        (tmp_path / "scan.json").write_text("[1, 2]")
        assert read_scan_total_files(tmp_path) == 0


class TestWriteRepositoryInfo:
    def test_round_trip(self, tmp_path):
        from quodeq.data.fs.project_files import (
            read_repository_info, write_repository_info,
        )

        assert write_repository_info(tmp_path, {"a": 1}) is True
        assert read_repository_info(tmp_path) == {"a": 1}

    def test_unwritable_returns_false(self, tmp_path):
        from quodeq.data.fs.project_files import write_repository_info

        assert write_repository_info(tmp_path / "no-such-dir", {"a": 1}) is False


class TestWriteScanJson:
    def test_creates_dir_and_writes(self, tmp_path):
        from quodeq.data.fs.project_files import write_scan_json

        scan = ScanData(
            file_tree=["a.py"], languages={"python": 1},
            scanned_at="2026-08-01T00:00:00Z", total_files=1, code_files=1,
        )
        out = tmp_path / "nested" / "dir"
        write_scan_json(scan, out)

        data = json.loads((out / "scan.json").read_text())
        assert data["total_files"] == 1
        assert data["file_tree"] == ["a.py"]


class TestServiceDelegation:
    def test_mark_onboarding_complete_writes_through_adapter(self, tmp_path):
        from quodeq.services.project_registration import mark_onboarding_complete

        (tmp_path / "repository_info.json").write_text("{}")
        with patch(
            "quodeq.services.project_registration.write_repository_info",
            return_value=True,
        ) as spy:
            mark_onboarding_complete(tmp_path)

        assert spy.call_count == 1
        assert spy.call_args.args[1].get("onboardingCompletedAt")

    def test_backfill_heal_writes_through_adapter(self, tmp_path):
        from quodeq.services._fs_project_helpers import _backfill_onboarding_field

        (tmp_path / "repository_info.json").write_text('{"createdAt": "2026-01-01"}')
        with patch(
            "quodeq.services._fs_project_helpers.write_repository_info",
            return_value=True,
        ) as spy:
            data = _backfill_onboarding_field(tmp_path)

        assert spy.call_count == 1
        assert data["onboardingCompletedAt"] == "2026-01-01"

    def test_scan_write_delegates_to_adapter(self, tmp_path):
        from quodeq.services import _fs_scan

        scan = ScanData(scanned_at="2026-08-01T00:00:00Z")
        with patch("quodeq.services._fs_scan.write_scan_json") as spy:
            _fs_scan._write_scan_json(scan, tmp_path)

        spy.assert_called_once_with(scan, tmp_path)
