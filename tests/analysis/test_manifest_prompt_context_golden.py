"""Character-for-character golden strings for manifest prompt-context rendering.

PROMPT BYTES ARE A CONTRACT: these strings are fed straight into the LLM
analysis prompt (and, for project_description, the compiled-standards
context too). Written BEFORE moving SourceManifest.to_prompt_context's body
and AnalysisTarget.project_description's body into
analysis/manifest_render.py (describe_target / render_manifest_prompt_context)
so the move can be verified byte-identical rather than just "still contains
the right words" (the existing substring-only tests in test_manifest.py
would pass even if wording drifted).
"""
from __future__ import annotations

from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest


def test_no_targets_with_language_stats_golden() -> None:
    manifest = SourceManifest(targets=[], total_files=17, language_stats={".py": 10, ".md": 7})
    assert manifest.to_prompt_context() == (
        "**Project type:** Unknown\n"
        "**Source files:** 17\n"
        "**Extension breakdown:** .py: 10, .md: 7"
    )


def test_no_targets_no_language_stats_golden() -> None:
    manifest = SourceManifest(targets=[], total_files=0, language_stats={})
    assert manifest.to_prompt_context() == (
        "**Project type:** Unknown\n"
        "**Source files:** 0"
    )


def test_single_target_golden() -> None:
    target = AnalysisTarget(
        name="python_backend", language="python", category="backend",
        frameworks=["Django", "REST"], total_files=42,
        source_files=["a.py"], language_stats={".py": 42},
    )
    manifest = SourceManifest(targets=[target], total_files=42, language_stats={".py": 42})
    assert manifest.to_prompt_context() == (
        "**Project type:** Python backend using Django, REST\n"
        "**Source files:** 42\n"
        "**Extension breakdown:** .py: 42"
    )


def test_multi_target_golden() -> None:
    rust = AnalysisTarget(
        name="rust_backend", language="rust", category="backend",
        total_files=85, source_files=["main.rs"], language_stats={".rs": 85},
    )
    dart = AnalysisTarget(
        name="dart_mobile", language="dart", category="mobile",
        frameworks=["Flutter"], total_files=235,
        source_files=["main.dart"], language_stats={".dart": 235},
    )
    manifest = SourceManifest(
        targets=[dart, rust], total_files=320,
        language_stats={".rs": 85, ".dart": 235},
    )
    assert manifest.to_prompt_context() == (
        "**Source files:** 320\n"
        "**Detected modules:**\n"
        "- Dart mobile using Flutter (235 files)\n"
        "- Rust backend (85 files)\n"
        "\n"
        "Analyze each file according to its language and project type.\n"
        "**Extension breakdown:** .dart: 235, .rs: 85"
    )


def test_project_description_golden() -> None:
    target = AnalysisTarget(
        name="python_backend", language="python", category="backend",
        frameworks=["Django", "REST"], total_files=42,
        source_files=["a.py"], language_stats={".py": 42},
    )
    manifest = SourceManifest(targets=[target], total_files=42, language_stats={".py": 42})
    assert target.project_description == "Python backend using Django, REST"
    # SourceManifest.project_description delegates to the primary target.
    assert manifest.project_description == "Python backend using Django, REST"
