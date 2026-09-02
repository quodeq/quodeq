"""Tests for the source manifest builder — prompt-context rendering and dict
serialization.

Split from test_manifest.py.
"""
from __future__ import annotations

from quodeq.analysis.manifest import AnalysisTarget, SourceManifest
from quodeq.analysis.manifest_render import render_manifest_prompt_context
from quodeq.analysis.manifest_serialization import manifest_to_dict


def test_to_prompt_context() -> None:
    target = AnalysisTarget(
        name="python_backend",
        language="python",
        category="backend",
        frameworks=["Django", "REST"],
        total_files=42,
        source_files=["a.py"],
        language_stats={".py": 42},
    )
    manifest = SourceManifest(targets=[target], total_files=42, language_stats={".py": 42})
    text = render_manifest_prompt_context(manifest)
    assert "Python" in text
    assert "42" in text
    assert "backend" in text
    assert "Django" in text


def test_to_dict() -> None:
    target = AnalysisTarget(
        name="typescript",
        language="typescript",
        total_files=10,
        source_files=["a.ts", "b.ts"],
        language_stats={".ts": 10},
    )
    manifest = SourceManifest(targets=[target], total_files=10, language_stats={".ts": 10})
    d = manifest_to_dict(manifest)
    assert d["language"] == "typescript"
    assert d["total_files"] == 10
    assert d["source_files_count"] == 2
    assert len(d["targets"]) == 1


def test_multi_target_prompt_context() -> None:
    """Multi-target manifest renders detected modules in prompt context."""
    rust = AnalysisTarget(
        name="rust_backend", language="rust", category="backend",
        total_files=85, source_files=["main.rs"],
        language_stats={".rs": 85},
    )
    dart = AnalysisTarget(
        name="dart_mobile", language="dart", category="mobile",
        frameworks=["Flutter"], total_files=235, source_files=["main.dart"],
        language_stats={".dart": 235},
    )
    manifest = SourceManifest(targets=[dart, rust], total_files=320, language_stats={".rs": 85, ".dart": 235})
    text = render_manifest_prompt_context(manifest)
    assert "320" in text
    assert "Detected modules" in text
    assert "Dart mobile" in text
    assert "Flutter" in text
    assert "Rust backend" in text
    assert "each file according to its language" in text
