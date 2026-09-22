"""build_cache_writer entries are self-describing: provenance, content hash, params."""
from __future__ import annotations

import json

from quodeq.config.paths import default_paths

from ._cache_writer_helpers import _make_config


def test_cache_writer_records_provenance_and_content_hash(tmp_path):
    """The written entry is self-describing: it stores the file_content_hash
    it was keyed under and a provenance block (model / prompts / standards /
    quodeq version) recording the volatile context it was produced under."""
    import quodeq
    from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer
    from quodeq.analysis.cache.dimension_helpers import (
        _hash_prompts_combined,
        build_cache_key_for_file,
    )
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.fingerprint import hash_file

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(CacheWriterSpec(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
        prompts_dir=default_paths().prompts_dir,
    ))
    write("Foo.kt", [])

    config = _make_config(src_root, model="sonnet", language="kotlin")
    key = build_cache_key_for_file(config, "Foo.kt", "flexibility")
    entry = LocalFileBackend(root=cache_root).get(key)
    assert entry is not None
    assert entry.file_content_hash == hash_file(src_root / "Foo.kt")
    prov = entry.provenance
    assert prov["model_id"] == "sonnet"
    assert prov["standards_hash"] == ""  # standards_dir=None
    assert prov["prompts_hash"] == _hash_prompts_combined(default_paths().prompts_dir)
    assert prov["quodeq_version"] == (quodeq.__version__ or "")


def test_cache_writer_provenance_folds_project_overrides(tmp_path):
    """The written standards_hash is the override-aware value (folding
    .quodeq/standards-overrides.json under src_root), matching what
    classify-time provenance computes — otherwise every later run would
    report phantom standards drift on entries this writer produced."""
    from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.fingerprint import hash_standards

    src_root = tmp_path / "src"
    (src_root / ".quodeq").mkdir(parents=True)
    (src_root / "Foo.kt").write_text("class Foo")
    (src_root / ".quodeq" / "standards-overrides.json").write_text(
        '{"version": 1, "overrides": {"F-ADP-1": {"max_lines": 60}}}'
    )
    standards_dir = tmp_path / "standards"
    (standards_dir / "compiled").mkdir(parents=True)
    (standards_dir / "compiled" / "flexibility.json").write_text('{"rule": "v1"}')

    cache_root = tmp_path / "cache"
    write = build_cache_writer(CacheWriterSpec(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=standards_dir,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
        prompts_dir=default_paths().prompts_dir,
    ))
    write("Foo.kt", [])

    config = _make_config(src_root, standards_dir=standards_dir, model="sonnet")
    key = build_cache_key_for_file(config, "Foo.kt", "flexibility")
    entry = LocalFileBackend(root=cache_root).get(key)
    assert entry is not None
    expected = hash_standards(standards_dir, "flexibility", src_root)
    assert entry.provenance["standards_hash"] == expected
    assert entry.provenance["standards_hash"] != hash_standards(
        standards_dir, "flexibility",
    )


def test_entry_is_self_describing_for_future_key_migration(tmp_path):
    """The self-describing guarantee: an entry stores EVERY field its key was
    computed from (content hash, path, dimension, params hash), so a future
    key change can be recomputed losslessly from the entry alone — no
    re-evaluation. This is what let the 3->4 change (language left the key)
    migrate in place. Regressing it silently breaks future migratability, so
    pin it."""
    from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.key import CacheKey, compute_key
    from quodeq.analysis.cache.local import LocalFileBackend

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(CacheWriterSpec(
        cache_root=cache_root, src_root=src_root, standards_dir=None,
        dimension="flexibility", model_id="sonnet", language="kotlin",
        prompts_dir=default_paths().prompts_dir,
    ))
    write("Foo.kt", [])

    config = _make_config(src_root, model="sonnet", language="kotlin")
    key = build_cache_key_for_file(config, "Foo.kt", "flexibility")
    entry = LocalFileBackend(root=cache_root).get(key)
    assert entry is not None

    # Recompute the key PURELY from stored entry fields (the migration
    # primitive — a real migration does this with schema_version + 1).
    recomputed = compute_key(CacheKey(
        schema_version=entry.schema_version,
        file_content_hash=entry.file_content_hash,
        file_path=entry.file_path,
        dimension=entry.dimension,
        params_hash=entry.params_hash,
    ))
    assert recomputed == key


def test_written_entry_records_effective_params(tmp_path):
    """The written entry's provenance carries effective_params -- the
    resolved threshold params (post-override) the findings were judged
    under. Mirrors test_cache_writer_provenance_folds_project_overrides's
    override fixture, but for a param'd requirement rather than max_lines
    on the standards JSON shape alone."""
    from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.local import LocalFileBackend

    src_root = tmp_path / "src"
    (src_root / ".quodeq").mkdir(parents=True)
    (src_root / "auth.py").write_text("class Auth: pass")
    (src_root / ".quodeq" / "standards-overrides.json").write_text(
        '{"version": 1, "overrides": {"M-ANA-2": {"max_lines": 60}}}'
    )
    standards_dir = tmp_path / "standards"
    (standards_dir / "compiled").mkdir(parents=True)
    (standards_dir / "compiled" / "maintainability.json").write_text(json.dumps({
        "id": "maintainability",
        "principles": [{"name": "P", "requirements": [{
            "id": "M-ANA-2", "text": "Max {max_lines} lines",
            "params": {"max_lines": {"default": 50, "min": 10, "max": 500}},
        }]}],
    }))

    cache_root = tmp_path / "cache"
    write = build_cache_writer(CacheWriterSpec(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=standards_dir,
        dimension="maintainability",
        model_id="m",
        language="python",
        prompts_dir=default_paths().prompts_dir,
    ))
    write("auth.py", [])

    config = _make_config(src_root, standards_dir=standards_dir, model="m", language="python")
    key = build_cache_key_for_file(config, "auth.py", "maintainability")
    entry = LocalFileBackend(root=cache_root).get(key)
    assert entry is not None
    assert entry.provenance["effective_params"]["M-ANA-2"]["max_lines"] == 60
    # Format 3: the non-default params hash the key was computed under is
    # stored on the entry, so a future key change never has to derive it.
    from quodeq.analysis.cache._key_provenance import build_cache_key_struct
    expected_params_hash = build_cache_key_struct(config, "auth.py", "maintainability").params_hash
    assert expected_params_hash != ""
    assert entry.params_hash == expected_params_hash
