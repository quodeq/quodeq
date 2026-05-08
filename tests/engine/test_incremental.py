"""Tests for incremental analysis — change detection and file classification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quodeq.analysis.incremental import detect_changed_files, ChangeDetectionResult, find_dependents, carry_forward_findings, classify_files, ClassificationInput, FileClassification, identify_backfill_files
from quodeq.analysis._incremental import _extract_files_from_jsonl


class TestDetectChangedFiles:
    def _make_fingerprint(self, files_content: dict[str, str], dimension="security"):
        return {
            "dimension": dimension,
            "git_commit": "abc123",
            "file_hashes": {f: hashlib.sha256(c.encode()).hexdigest() for f, c in files_content.items()},
            "standards_checksum": "std_hash_123",
            "analyzed_files": sorted(files_content.keys()),
            "timestamp": "2026-01-01",
        }

    def test_detects_changed_file(self, tmp_path):
        prev = self._make_fingerprint({"a.py": "old_content", "b.py": "same"})
        (tmp_path / "a.py").write_text("new_content")
        (tmp_path / "b.py").write_text("same")
        result = detect_changed_files(src=tmp_path, files=["a.py", "b.py"], prev_fingerprint=prev, standards_dir=None, dimension="security")
        assert "a.py" in result.changed
        assert "b.py" not in result.changed

    def test_detects_new_file(self, tmp_path):
        prev = self._make_fingerprint({"a.py": "content"})
        (tmp_path / "a.py").write_text("content")
        (tmp_path / "new.py").write_text("brand new")
        result = detect_changed_files(src=tmp_path, files=["a.py", "new.py"], prev_fingerprint=prev, standards_dir=None, dimension="security")
        assert "new.py" in result.changed
        assert "a.py" not in result.changed

    def test_standards_change_triggers_full(self, tmp_path):
        prev = self._make_fingerprint({"a.py": "content"})
        prev["standards_checksum"] = "old_standards"
        (tmp_path / "a.py").write_text("content")
        standards = tmp_path / "standards" / "compiled"
        standards.mkdir(parents=True)
        (standards / "security.json").write_text('{"new": true}')
        result = detect_changed_files(src=tmp_path, files=["a.py"], prev_fingerprint=prev, standards_dir=tmp_path / "standards", dimension="security")
        assert result.full_reanalysis is True

    def test_no_previous_fingerprint_returns_full(self, tmp_path):
        result = detect_changed_files(src=tmp_path, files=["a.py"], prev_fingerprint=None, standards_dir=None, dimension="security")
        assert result.full_reanalysis is True

    def test_no_changes_returns_empty(self, tmp_path):
        (tmp_path / "a.py").write_text("same")
        prev = self._make_fingerprint({"a.py": "same"})
        result = detect_changed_files(src=tmp_path, files=["a.py"], prev_fingerprint=prev, standards_dir=None, dimension="security")
        assert len(result.changed) == 0
        assert result.full_reanalysis is False


class TestDetectPromptsChanged:
    """Selective prompt invalidation: only rules-bearing files trigger
    full re-analysis. Framing/runner-prompt changes carry forward.
    """

    def _make_fingerprint(self, prompts_checksum):
        return {
            "dimension": "security",
            "git_commit": "abc",
            "file_hashes": {},
            "standards_checksum": None,
            "prompts_checksum": prompts_checksum,
            "timestamp": "2026-01-01",
        }

    def test_rules_file_change_triggers_full(self, tmp_path, monkeypatch):
        # evaluation_rules.md is the rules-bearing file → any change
        # invalidates carry-forward.
        from quodeq.analysis import _incr_change_detection as mod
        monkeypatch.setattr(mod, "_hash_prompts_map", lambda: {
            "evaluation_rules.md": "NEW",
            "api_prompt.md": "same",
        })
        prev = self._make_fingerprint({
            "evaluation_rules.md": "OLD",
            "api_prompt.md": "same",
        })
        result = detect_changed_files(
            src=tmp_path, files=[], prev_fingerprint=prev,
            standards_dir=None, dimension="security",
        )
        assert result.full_reanalysis is True
        assert "evaluation_rules.md" in result.reason

    def test_non_rules_file_change_does_not_trigger(self, tmp_path, monkeypatch):
        # api_prompt.md is framing — a change shouldn't force full re-analysis,
        # so prior findings carry forward.
        from quodeq.analysis import _incr_change_detection as mod
        monkeypatch.setattr(mod, "_hash_prompts_map", lambda: {
            "evaluation_rules.md": "same",
            "api_prompt.md": "NEW",
            "cli_subagent_prompt.md": "NEW",
        })
        prev = self._make_fingerprint({
            "evaluation_rules.md": "same",
            "api_prompt.md": "OLD",
            "cli_subagent_prompt.md": "OLD",
        })
        result = detect_changed_files(
            src=tmp_path, files=[], prev_fingerprint=prev,
            standards_dir=None, dimension="security",
        )
        assert result.full_reanalysis is False

    def test_legacy_string_format_still_triggers(self, tmp_path, monkeypatch):
        # Pre-split fingerprints stored a single concatenated hash. The reader
        # falls back to comparing legacy hashes to keep the conservative
        # behavior until the next run upgrades the fingerprint format.
        from quodeq.analysis import _incr_change_detection as mod
        monkeypatch.setattr(mod, "_hash_prompts", lambda: "NEW_LEGACY_HASH")
        prev = self._make_fingerprint("OLD_LEGACY_HASH")
        result = detect_changed_files(
            src=tmp_path, files=[], prev_fingerprint=prev,
            standards_dir=None, dimension="security",
        )
        assert result.full_reanalysis is True
        assert "legacy" in result.reason

    def test_legacy_string_format_unchanged_does_not_trigger(self, tmp_path, monkeypatch):
        from quodeq.analysis import _incr_change_detection as mod
        monkeypatch.setattr(mod, "_hash_prompts", lambda: "SAME_HASH")
        prev = self._make_fingerprint("SAME_HASH")
        result = detect_changed_files(
            src=tmp_path, files=[], prev_fingerprint=prev,
            standards_dir=None, dimension="security",
        )
        assert result.full_reanalysis is False

    def test_missing_prompts_checksum_does_not_trigger(self, tmp_path):
        prev = self._make_fingerprint(None)
        result = detect_changed_files(
            src=tmp_path, files=[], prev_fingerprint=prev,
            standards_dir=None, dimension="security",
        )
        assert result.full_reanalysis is False


class TestFindDependents:
    def test_finds_files_that_import_changed_file(self, tmp_path):
        (tmp_path / "auth.py").write_text("")
        (tmp_path / "routes.py").write_text("from auth import login\n")
        (tmp_path / "utils.py").write_text("")
        dependents = find_dependents(changed={"auth.py"}, files=["auth.py", "routes.py", "utils.py"], src=tmp_path, language="python")
        assert "routes.py" in dependents
        assert "utils.py" not in dependents
        assert "auth.py" not in dependents

    def test_no_dependents(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        dependents = find_dependents(changed={"a.py"}, files=["a.py", "b.py"], src=tmp_path, language="python")
        assert len(dependents) == 0

    def test_one_level_deep_only(self, tmp_path):
        (tmp_path / "core.py").write_text("")
        (tmp_path / "mid.py").write_text("import core\n")
        (tmp_path / "top.py").write_text("import mid\n")
        dependents = find_dependents(changed={"core.py"}, files=["core.py", "mid.py", "top.py"], src=tmp_path, language="python")
        assert "mid.py" in dependents
        assert "top.py" not in dependents


class TestCarryForwardFindings:
    def test_copies_unchanged_file_findings(self, tmp_path):
        prev_jsonl = tmp_path / "prev.jsonl"
        findings = [
            {"p": "Conf", "d": "security", "t": "violation", "file": "unchanged.py", "line": 1, "w": "test"},
            {"p": "Int", "d": "security", "t": "compliance", "file": "changed.py", "line": 5, "w": "test2"},
            {"p": "Conf", "d": "security", "t": "violation", "file": "unchanged.py", "line": 10, "w": "test3"},
        ]
        prev_jsonl.write_text("\n".join(json.dumps(f) for f in findings))
        output_jsonl = tmp_path / "output.jsonl"
        count = carry_forward_findings(prev_jsonl, output_jsonl, {"unchanged.py"})
        assert count == 2
        lines = output_jsonl.read_text().strip().split("\n")
        assert len(lines) == 2
        assert all("unchanged.py" in line for line in lines)

    def test_skips_changed_file_findings(self, tmp_path):
        prev_jsonl = tmp_path / "prev.jsonl"
        prev_jsonl.write_text(json.dumps({"p": "X", "d": "security", "t": "violation", "file": "changed.py", "line": 1, "w": "old"}) + "\n")
        output_jsonl = tmp_path / "output.jsonl"
        count = carry_forward_findings(prev_jsonl, output_jsonl, {"other.py"})
        assert count == 0

    def test_missing_prev_jsonl(self, tmp_path):
        count = carry_forward_findings(tmp_path / "nonexistent.jsonl", tmp_path / "output.jsonl", {"a.py"})
        assert count == 0


class TestClassifyFiles:
    def test_classifies_changed_dependent_unchanged(self, tmp_path):
        (tmp_path / "changed.py").write_text("new_code")
        (tmp_path / "dependent.py").write_text("from changed import foo\n")
        (tmp_path / "unchanged.py").write_text("same")
        prev_fp = {
            "dimension": "security", "git_commit": None,
            "file_hashes": {
                "changed.py": hashlib.sha256(b"old_code").hexdigest(),
                "dependent.py": hashlib.sha256(b"from changed import foo\n").hexdigest(),
                "unchanged.py": hashlib.sha256(b"same").hexdigest(),
            },
            "standards_checksum": None,
            "analyzed_files": ["changed.py", "dependent.py", "unchanged.py"],
        }
        result = classify_files(inputs=ClassificationInput(
            src=tmp_path, files=["changed.py", "dependent.py", "unchanged.py"],
            prev_fingerprint=prev_fp, standards_dir=None, dimension="security", language="python"))
        assert "changed.py" in result.to_analyze
        assert "dependent.py" in result.to_analyze
        assert "unchanged.py" in result.unchanged

    def test_full_reanalysis_returns_all(self, tmp_path):
        result = classify_files(inputs=ClassificationInput(
            src=tmp_path, files=["a.py", "b.py"],
            prev_fingerprint=None, standards_dir=None, dimension="security", language="python"))
        assert set(result.to_analyze) == {"a.py", "b.py"}
        assert len(result.unchanged) == 0
        assert result.full_reanalysis is True


class TestIdentifyBackfillFiles:
    def test_backfill_excludes_previously_analyzed(self):
        all_files = ["a.py", "b.py", "c.py", "d.py"]
        prev_analyzed = ["a.py", "b.py"]
        already_queued = {"c.py"}
        result = identify_backfill_files(all_files, prev_analyzed, already_queued)
        assert result == ["d.py"]

    def test_backfill_returns_empty_when_all_covered(self):
        all_files = ["a.py", "b.py"]
        prev_analyzed = ["a.py", "b.py"]
        result = identify_backfill_files(all_files, prev_analyzed, set())
        assert result == []

    def test_backfill_preserves_input_order(self):
        all_files = ["z.py", "a.py", "m.py"]
        prev_analyzed = []
        result = identify_backfill_files(all_files, prev_analyzed, set())
        assert result == ["z.py", "a.py", "m.py"]


class TestIncrementalRunnerIntegration:
    def test_incremental_file_filter_on_options(self):
        from quodeq.analysis.runner import AnalysisOptions
        opts = AnalysisOptions(incremental=True)
        assert opts.incremental_file_filter is None
        opts.incremental_file_filter = {"changed.py"}
        assert "changed.py" in opts.incremental_file_filter
        opts.incremental_file_filter = None
        assert opts.incremental_file_filter is None

    def test_no_changes_classify(self, tmp_path):
        (tmp_path / "a.py").write_text("same")
        prev_fp = {
            "dimension": "security", "git_commit": None,
            "file_hashes": {"a.py": hashlib.sha256(b"same").hexdigest()},
            "standards_checksum": None,
            "analyzed_files": ["a.py"],
        }
        result = classify_files(inputs=ClassificationInput(
            src=tmp_path, files=["a.py"], prev_fingerprint=prev_fp,
            standards_dir=None, dimension="security", language="python"))
        assert len(result.to_analyze) == 0
        assert result.unchanged == {"a.py"}


class TestExtractFilesFromJsonl:
    def test_extracts_unique_file_paths(self, tmp_path):
        """Extracts unique file paths from evidence JSONL."""
        jsonl = tmp_path / "security_evidence.jsonl"
        jsonl.write_text(
            '{"p":"Mod","t":"violation","file":"a.py","line":1}\n'
            '{"p":"Mod","t":"compliance","file":"b.py","line":2}\n'
            '{"p":"Mod","t":"violation","file":"a.py","line":5}\n'
        )
        files = _extract_files_from_jsonl(jsonl)
        assert files == {"a.py", "b.py"}

    def test_missing_file_returns_empty(self, tmp_path):
        """Non-existent JSONL returns empty set."""
        files = _extract_files_from_jsonl(tmp_path / "missing.jsonl")
        assert files == set()

    def test_skips_malformed_lines(self, tmp_path):
        """Malformed JSON lines are skipped gracefully."""
        jsonl = tmp_path / "security_evidence.jsonl"
        jsonl.write_text(
            '{"p":"Mod","t":"violation","file":"a.py","line":1}\n'
            'not valid json\n'
            '\n'
            '{"p":"Mod","t":"violation","line":1}\n'
            '{"p":"Mod","t":"violation","file":"","line":1}\n'
        )
        files = _extract_files_from_jsonl(jsonl)
        assert files == {"a.py"}

    def test_empty_file_returns_empty(self, tmp_path):
        """Empty JSONL returns empty set."""
        jsonl = tmp_path / "security_evidence.jsonl"
        jsonl.write_text("")
        files = _extract_files_from_jsonl(jsonl)
        assert files == set()


