"""Provenance drift detection, its user-facing formatting, and prompts_dir stamping."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from quodeq.analysis.cache import CacheEntry, LocalFileBackend
from quodeq.analysis.cache._persist_watcher import CachePersistTarget
from quodeq.analysis.cache.dimension_helpers import (
    ClassifyResult,
    build_cache_key_for_file,
    classify_files_via_cache,
    format_provenance_drift,
    persist_dispatch_results,
)

from ._dimension_helpers_helpers import (
    _hash_inputs,
    _make_config,
    _write_compiled_standards,
    _write_files,
    _write_project_overrides,
)


# ============================================================
# provenance drift (reuse across model/standards/prompts boundary)
# ============================================================

class TestProvenanceDrift:
    def _seed(self, cache, config, files, *, provenance):
        for f in files:
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=3, findings=[{"file": f}],
                files_read=1, file_path=f, dimension="security",
                model_id=provenance.get("model_id", ""), provenance=provenance,
            ))

    def test_reports_model_drift_across_hits(self, tmp_path: Path, cache: LocalFileBackend):
        files = _write_files(tmp_path / "src", {"a.py": "x", "b.py": "y"})
        config = _make_config(tmp_path / "src", model="new-model")
        # Seed entries produced under a different model. Other provenance
        # fields are blank, so only the model field is a known difference.
        self._seed(cache, config, files, provenance={
            "model_id": "old-model", "standards_hash": "",
            "prompts_hash": "", "quodeq_version": "",
        })
        result = classify_files_via_cache(config, "security", files, cache)
        assert result.misses == []
        drift = result.provenance_drift
        assert drift["model_id"]["count"] == 2
        assert drift["model_id"]["from"] == "old-model"
        assert drift["model_id"]["to"] == "new-model"
        # Blank (unknown) fields are never reported as drift.
        assert "standards_hash" not in drift
        assert "prompts_hash" not in drift

    def test_ignores_unknown_provenance(self, tmp_path: Path, cache: LocalFileBackend):
        # A legacy / empty-provenance entry must not be claimed as drift —
        # we can't know what it was produced under.
        files = _write_files(tmp_path / "src", {"a.py": "x"})
        config = _make_config(tmp_path / "src", model="new-model")
        self._seed(cache, config, files, provenance={})
        result = classify_files_via_cache(config, "security", files, cache)
        assert result.misses == []
        assert result.provenance_drift == {}

    def test_reports_standards_drift_when_overrides_change(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        # Threshold overrides fold into the standards hash: entries produced
        # before a project tuned .quodeq/standards-overrides.json must show
        # standards drift on reuse — the compiled JSON alone is unchanged.
        from quodeq.analysis.fingerprint import _hash_standards

        src = tmp_path / "src"
        files = _write_files(src, {"a.py": "x"})
        standards_dir = tmp_path / "standards"
        _write_compiled_standards(standards_dir, "security", '{"rule": "v1"}')
        config = _make_config(src, standards_dir=standards_dir)
        pre_override = _hash_standards(standards_dir, "security") or ""
        self._seed(cache, config, files, provenance={
            "model_id": "test-model", "standards_hash": pre_override,
            "prompts_hash": "", "quodeq_version": "",
        })

        _write_project_overrides(
            src, '{"version": 1, "overrides": {"S-INJ-1": {"max_lines": 60}}}',
        )
        result = classify_files_via_cache(config, "security", files, cache)

        # Reuse still happens (permissive key) but is flagged, not silent.
        assert result.misses == []
        assert result.provenance_drift["standards_hash"]["count"] == 1

    def test_no_drift_when_provenance_matches(self, tmp_path: Path, cache: LocalFileBackend):
        files = _write_files(tmp_path / "src", {"a.py": "x"})
        config = _make_config(tmp_path / "src", model="same-model")
        self._seed(cache, config, files, provenance={
            "model_id": "same-model", "standards_hash": "",
            "prompts_hash": "", "quodeq_version": "",
        })
        result = classify_files_via_cache(config, "security", files, cache)
        assert result.provenance_drift == {}


class TestFormatProvenanceDrift:
    def test_names_model_and_standards_with_counts(self):
        drift = {
            "model_id": {"count": 240, "from": "claude-sonnet-4", "to": "claude-opus-4"},
            "standards_hash": {"count": 240, "from": "s3", "to": "s4"},
        }
        msg = format_provenance_drift(drift, reused=240)
        assert "240" in msg
        assert "model" in msg
        assert "claude-sonnet-4" in msg and "claude-opus-4" in msg
        assert "standards" in msg
        # Opaque standards hashes are not dumped into user-facing text.
        assert "s3" not in msg
        # No em-dash in user-facing strings (repo convention).
        assert "—" not in msg

    def test_empty_when_no_drift(self):
        assert format_provenance_drift({}, reused=100) == ""

    def test_shows_version_transition_suppresses_all_hashes_in_order(self):
        # Covers the other two field branches: quodeq_version (human-value,
        # shows from->to) and prompts_hash (opaque, value suppressed). Pins
        # that NEITHER the 'from' nor 'to' of an opaque hash leaks, and that
        # fields render in _PROV_FIELDS order.
        drift = {
            "model_id": {"count": 3, "from": "sonnet", "to": "opus"},
            "standards_hash": {"count": 3, "from": "s3", "to": "s4"},
            "prompts_hash": {"count": 3, "from": "p3", "to": "p4"},
            "quodeq_version": {"count": 3, "from": "1.0.0", "to": "1.1.2"},
        }
        msg = format_provenance_drift(drift, reused=3)
        # Human-value fields show the transition.
        assert "1.0.0" in msg and "1.1.2" in msg
        assert "quodeq version" in msg
        assert "prompts" in msg
        # Opaque hashes never leak — neither 'from' nor 'to'.
        for opaque in ("s3", "s4", "p3", "p4"):
            assert opaque not in msg
        # Rendered in _PROV_FIELDS order: model, standards, prompts, version.
        assert (
            msg.index("model")
            < msg.index("standards")
            < msg.index("prompts")
            < msg.index("quodeq version")
        )


# ============================================================
# prompts_dir injection ([35]/[36]): provenance hashes flow from
# RunConfig.prompts_dir, and all three stamping sites agree.
# ============================================================

class TestPromptsDirProvenance:
    def _prompts_dir(self, tmp_path: Path) -> Path:
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        (prompts / "rules.md").write_text("# rule one")
        return prompts

    def test_current_provenance_hashes_injected_prompts_dir(self, tmp_path: Path):
        from quodeq.analysis.cache.dimension_helpers import (
            _current_provenance,
            _hash_prompts_combined,
        )

        prompts = self._prompts_dir(tmp_path)
        _write_files(tmp_path / "src", {"a.py": "x"})
        config = replace(_make_config(tmp_path / "src"), prompts_dir=prompts)

        prov = _current_provenance(config, "security")
        expected = _hash_prompts_combined(prompts)
        assert expected  # the temp dir has a rules-bearing prompt
        assert prov["prompts_hash"] == expected

    def test_persist_stamps_the_injected_prompts_dir(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        from quodeq.analysis.cache.dimension_helpers import _hash_prompts_combined

        prompts = self._prompts_dir(tmp_path)
        files = _write_files(tmp_path / "src", {"a.py": "x"})
        config = replace(
            _make_config(tmp_path / "src", work_dir=tmp_path / "work"),
            prompts_dir=prompts,
        )
        miss_keys = {f: build_cache_key_for_file(config, f, "security") for f in files}
        jsonl = tmp_path / "work" / "security_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text(
            json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n"
        )

        persist_dispatch_results(
            config, "security",
            classify=ClassifyResult(misses=files, miss_keys=miss_keys),
            provenance=_hash_inputs(config, "security"),
            target=CachePersistTarget(jsonl_path=jsonl, cache=cache),
        )

        entry = cache.get(miss_keys["a.py"])
        assert entry is not None
        assert entry.provenance["prompts_hash"] == _hash_prompts_combined(prompts)

    def test_cache_writer_agrees_with_classify_time_provenance(self, tmp_path: Path):
        """The synchronous cache writer and classify's _current_provenance
        must stamp the SAME prompts_hash for the same prompts_dir, or reused
        entries report phantom prompts drift."""
        from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer
        from quodeq.analysis.cache.dimension_helpers import _current_provenance
        from quodeq.analysis.cache.local import LocalFileBackend

        prompts = self._prompts_dir(tmp_path)
        _write_files(tmp_path / "src", {"a.py": "x"})
        config = replace(_make_config(tmp_path / "src"), prompts_dir=prompts)

        cache_root = tmp_path / "cache"
        write = build_cache_writer(CacheWriterSpec(
            cache_root=cache_root,
            src_root=tmp_path / "src",
            standards_dir=None,
            dimension="security",
            model_id="test-model",
            language="python",
            prompts_dir=config.prompts_dir,
        ))
        write("a.py", [])

        key = build_cache_key_for_file(config, "a.py", "security")
        entry = LocalFileBackend(root=cache_root).get(key)
        assert entry is not None
        current = _current_provenance(config, "security")
        assert entry.provenance["prompts_hash"] == current["prompts_hash"]
        assert current["prompts_hash"]  # non-empty: the hash is real, not two blanks
