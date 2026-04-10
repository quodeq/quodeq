"""Tests for prompt builder."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis.prompts.builder import (
    PromptContext,
    build_analysis_prompt,
    build_consolidated_prompt,
    load_template,
    render_compiled_standards,
    render_dimensions,
)


def _sample_dimensions():
    return {
        "applies": [
            {"id": "security", "weight": 1.2, "iso_25010": "Security", "source": "OWASP"},
            {"id": "maintainability", "weight": 1.0, "iso_25010": "Maintainability"},
        ],
        "excludes": ["usability"],
    }


# ---------------------------------------------------------------------------
# render_compiled_standards
# ---------------------------------------------------------------------------

class TestRenderCompiledStandards:
    def test_renders_principles_and_requirements(self, tmp_path):
        compiled = {
            "id": "reliability",
            "principles": [
                {
                    "name": "Fault Tolerance",
                    "source": "iso25010",
                    "requirements": [
                        {"id": "R-FT-1", "source": "iso25010",
                         "text": "Exceptions MUST be caught and handled", "refs": []},
                        {"id": "R-FT-2", "source": "iso25010",
                         "text": "Null dereferences MUST be guarded", "refs": []},
                    ],
                },
                {
                    "name": "Maturity",
                    "source": "iso25010",
                    "requirements": [
                        {"id": "R-MAT-1", "source": "iso25010",
                         "text": "All public functions MUST have tests", "refs": []},
                    ],
                },
            ],
        }
        (tmp_path / "reliability.json").write_text(json.dumps(compiled))
        text = render_compiled_standards(tmp_path, "reliability")
        assert "### Fault Tolerance" in text
        assert "**R-FT-1**" in text
        assert "Exceptions MUST be caught and handled" in text
        assert "**R-FT-2**" in text
        assert "### Maturity" in text
        assert "**R-MAT-1**" in text
        assert "CWE-" not in text

    def test_missing_dimension(self, tmp_path):
        text = render_compiled_standards(tmp_path, "nonexistent")
        assert "No compiled standards" in text

    def test_empty_requirements(self, tmp_path):
        compiled = {"id": "test", "principles": [{"name": "Empty", "source": "iso25010", "requirements": []}]}
        (tmp_path / "test.json").write_text(json.dumps(compiled))
        text = render_compiled_standards(tmp_path, "test")
        assert "Empty" not in text


# ---------------------------------------------------------------------------
# render_dimensions
# ---------------------------------------------------------------------------

class TestRenderDimensions:
    def test_basic_rendering(self):
        text = render_dimensions(_sample_dimensions(), "security")
        assert "security" in text
        assert "1.2" in text
        assert "OWASP" in text

    def test_missing_dimension(self):
        text = render_dimensions(_sample_dimensions(), "nonexistent")
        assert "not configured" in text

    def test_renders_weight_and_iso(self):
        text = render_dimensions(_sample_dimensions(), "security")
        assert "**Weight:** 1.2" in text
        assert "**ISO 25010:** Security" in text


# ---------------------------------------------------------------------------
# load_template
# ---------------------------------------------------------------------------

def test_load_template():
    template = load_template()
    assert "{{DISCIPLINE}}" in template
    assert "{{STANDARDS_CHECKLIST}}" in template
    assert "{{DIMENSION}}" in template


def test_load_template_custom_path(tmp_path):
    custom = tmp_path / "test.md"
    custom.write_text("Hello {{NAME}}")
    text = load_template(custom)
    assert text == "Hello {{NAME}}"


# ---------------------------------------------------------------------------
# build_analysis_prompt
# ---------------------------------------------------------------------------

class TestBuildAnalysisPrompt:
    def test_substitutes_all_variables(self, tmp_path):
        from quodeq.analysis.manifest import SourceManifest

        # Create minimal compiled standards
        compiled_dir = tmp_path / "compiled"
        compiled_dir.mkdir()
        compiled = {
            "id": "security",
            "principles": [
                {
                    "name": "Confidentiality",
                    "source": "iso25010",
                    "requirements": [
                        {"id": "S-CON-1", "source": "iso25010",
                         "text": "Secrets MUST NOT be hardcoded in source", "refs": []}
                    ],
                },
            ],
        }
        (compiled_dir / "security.json").write_text(json.dumps(compiled))

        from quodeq.analysis.manifest import AnalysisTarget
        target = AnalysisTarget(name="typescript", language="typescript", total_files=42)
        manifest = SourceManifest(targets=[target], total_files=42)
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            PromptContext(
                language="typescript",
                repo_name="my-app",
                date_str="2026-03-06",
                dimension="security",
                source_file_count=42,
                dimensions_data=_sample_dimensions(),
                standards_dir=tmp_path,
                manifest=manifest,
            ),
        )
        assert "{{" not in prompt  # all placeholders resolved
        assert "my-app" in prompt
        assert "2026-03-06" in prompt
        assert "Typescript" in prompt  # from manifest project_description
        assert "42" in prompt
        assert "Confidentiality" in prompt
        assert "S-CON-1" in prompt
        assert "Secrets MUST NOT be hardcoded" in prompt
        assert "security" in prompt

    def test_no_manifest_shows_no_guidance(self):
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            PromptContext(
                language="typescript",
                repo_name="test",
                date_str="2026-03-06",
                dimension="security",
                source_file_count=10,
                dimensions_data=_sample_dimensions(),
            ),
        )
        assert "No additional guidance" in prompt

    @staticmethod
    def _create_security_compiled(compiled_dir: Path) -> None:
        """Write a minimal compiled security standard to *compiled_dir*."""
        compiled_dir.mkdir(parents=True, exist_ok=True)
        compiled = {
            "id": "security",
            "principles": [
                {
                    "name": "Confidentiality",
                    "source": "iso25010",
                    "requirements": [
                        {"id": "S-CON-1", "source": "iso25010",
                         "text": "Secrets MUST NOT be hardcoded in source", "refs": []}
                    ],
                },
            ],
        }
        (compiled_dir / "security.json").write_text(json.dumps(compiled))

    def test_standards_written_to_file_when_work_dir_set(self, tmp_path):
        """When work_dir is provided, standards are written to a file and the
        prompt contains a read instruction instead of inline content."""
        from quodeq.analysis.manifest import AnalysisTarget, SourceManifest

        self._create_security_compiled(tmp_path / "standards" / "compiled")
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        target = AnalysisTarget(name="typescript", language="typescript", total_files=42)
        manifest = SourceManifest(targets=[target], total_files=42)
        prompt = build_analysis_prompt(
            load_template(),
            PromptContext(
                language="typescript",
                repo_name="my-app",
                date_str="2026-03-06",
                dimension="security",
                source_file_count=42,
                dimensions_data=_sample_dimensions(),
                standards_dir=tmp_path / "standards",
                manifest=manifest,
                work_dir=work_dir,
            ),
        )
        assert "Secrets MUST NOT be hardcoded" not in prompt
        assert "FIRST ACTION" in prompt
        assert ".quodeq_standards_security.md" in prompt

        standards_file = work_dir / ".quodeq_standards_security.md"
        assert standards_file.exists()
        content = standards_file.read_text()
        assert "### Confidentiality" not in content
        assert '"S-CON-1"' in content
        assert '"Secrets MUST NOT be hardcoded' in content

    def test_prompt_hash_present(self):
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            PromptContext(
                language="typescript",
                repo_name="test",
                date_str="2026-03-06",
                dimension="security",
                source_file_count=10,
                dimensions_data=_sample_dimensions(),
            ),
        )
        assert "PROMPT_HASH" not in prompt


# ---------------------------------------------------------------------------
# build_consolidated_prompt
# ---------------------------------------------------------------------------

class TestBuildConsolidatedPrompt:
    def test_includes_all_dimension_standards(self, tmp_path):
        compiled = tmp_path / "compiled"
        compiled.mkdir()
        for dim, req_id in [("security", "S-CON-1"), ("maintainability", "M-MOD-1")]:
            data = {"id": dim, "principles": [{"name": "Test", "source": "iso25010",
                    "requirements": [{"id": req_id, "source": "iso25010",
                    "text": f"Test req for {dim}", "refs": []}]}]}
            (compiled / f"{dim}.json").write_text(json.dumps(data))

        prompt = build_consolidated_prompt(
            dimensions=["security", "maintainability"],
            context=PromptContext(
                language="python", repo_name="test", date_str="2026-03-22",
                dimension="consolidated",
                source_file_count=20,
                dimensions_data=_sample_dimensions(),
                standards_dir=tmp_path,
            ),
        )
        assert "S-CON-1" in prompt
        assert "M-MOD-1" in prompt
        assert "security" in prompt.lower()
        assert "maintainability" in prompt.lower()

    def test_dimension_list_in_prompt(self, tmp_path):
        compiled = tmp_path / "compiled"
        compiled.mkdir()
        prompt = build_consolidated_prompt(
            dimensions=["security", "reliability"],
            context=PromptContext(
                language="python", repo_name="test", date_str="2026-03-22",
                dimension="consolidated",
                source_file_count=10,
                dimensions_data=_sample_dimensions(),
                standards_dir=tmp_path,
            ),
        )
        assert "security, reliability" in prompt
