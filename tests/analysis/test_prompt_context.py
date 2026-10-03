import json
from pathlib import Path
from unittest.mock import patch

from quodeq.analysis.prompts._context import PromptContext
from quodeq.analysis.prompts.builder import (
    build_analysis_prompt,
    build_consolidated_prompt,
    load_template,
    render_all_standards,
    render_compiled_standards,
    render_previous_findings_section,
)


def _sample_dimensions():
    return {
        "applies": [
            {"id": "security", "weight": 1.2, "iso_25010": "Security", "source": "OWASP"},
        ],
        "excludes": [],
    }


def _write_security_compiled(compiled_dir: Path) -> None:
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
                     "text": "Secrets MUST NOT be hardcoded in source", "refs": []},
                ],
            },
        ],
    }
    (compiled_dir / "security.json").write_text(json.dumps(compiled))


def test_prompt_context_default_previous_findings():
    ctx = PromptContext(
        language="python", repo_name="test", date_str="2026-01-01",
        dimension="security", source_file_count=10, dimensions_data={},
    )
    assert ctx.previous_findings == []


def test_prompt_context_with_previous_findings():
    findings = [
        {"p": "Security", "t": "violation", "file": "a.py", "line": 1, "reason": "test"},
    ]
    ctx = PromptContext(
        language="python", repo_name="test", date_str="2026-01-01",
        dimension="security", source_file_count=10, dimensions_data={},
        previous_findings=findings,
    )
    assert ctx.previous_findings == findings


def test_render_previous_findings_empty():
    assert render_previous_findings_section([]) == ""


def test_render_previous_findings_groups_by_file():
    findings = [
        {"p": "Security", "t": "violation", "file": "a.py", "line": 42, "req": "S-CON-3", "reason": "hardcoded creds"},
        {"p": "Security", "t": "compliance", "file": "a.py", "line": 55, "req": "S-CON-5", "reason": "good validation"},
        {"p": "Maintainability", "t": "violation", "file": "b.py", "line": 100, "req": "P-MOD-1", "reason": "long function"},
    ]
    result = render_previous_findings_section(findings)
    assert "### a.py" in result
    assert "### b.py" in result
    assert "[violation] S-CON-3" in result
    assert "[compliance] S-CON-5" in result
    assert "[violation] P-MOD-1" in result
    assert "hardcoded creds" in result
    assert "Previous findings" in result


def test_render_previous_findings_no_file_key():
    findings = [{"p": "X", "t": "violation", "reason": "no file"}]
    result = render_previous_findings_section(findings)
    assert "### (unknown file)" in result


def test_build_subagent_prompt_passes_inline_findings():
    from unittest.mock import MagicMock

    from quodeq.analysis.subagents._prompts import build_subagent_prompt

    findings = [{"file": "a.py", "p": "S", "t": "violation", "line": 1, "reason": "test"}]
    ctx = MagicMock()
    ctx.subagent_template = "{{DIMENSION}} analysis"
    ctx.date_str = "2026-01-01"
    ctx.dimensions_data = {}

    config = MagicMock()
    config.language = "python"
    config.src = "/test"
    config.source_file_count = 10
    config.standards_dir = None
    config.evaluators_dir = None
    config.manifest = None
    config.target = None
    config.work_dir = None

    result = build_subagent_prompt(config, "security", ctx, inline_findings=findings)
    assert "Previous findings" in result
    assert "a.py" in result


def test_build_analysis_prompt_uses_injected_overrides_loader(tmp_path):
    """PromptContext.overrides_loader is a call-time seam: when set,
    the standards checklist must be rendered with the loader's overrides
    instead of calling the concrete load_project_overrides."""
    _write_security_compiled(tmp_path / "standards" / "compiled")
    loader_calls: list = []
    sentinel_overrides = {"S-CON-1": {"floorMajor": 9.0}}

    def _fake_loader(project_root):
        loader_calls.append(project_root)
        return sentinel_overrides

    with patch(
        "quodeq.analysis.prompts.builder.load_project_overrides",
        side_effect=AssertionError("the concrete loader must not be called"),
    ), patch(
        "quodeq.analysis.prompts.builder.render_compiled_standards",
        wraps=render_compiled_standards,
    ) as spy_render:
        build_analysis_prompt(
            load_template(),
            PromptContext(
                language="typescript", repo_name="my-app", date_str="2026-03-06",
                dimension="security", source_file_count=42,
                dimensions_data=_sample_dimensions(),
                standards_dir=tmp_path / "standards",
                project_root=tmp_path,
                overrides_loader=_fake_loader,
            ),
        )
    assert loader_calls == [tmp_path]
    assert spy_render.call_args.kwargs["overrides"] is sentinel_overrides


def test_build_consolidated_prompt_uses_injected_overrides_loader(tmp_path):
    """Same seam, consolidated-prompt path."""
    compiled = tmp_path / "compiled"
    compiled.mkdir()
    data = {"id": "security", "principles": [{"name": "Test", "source": "iso25010",
            "requirements": [{"id": "S-CON-1", "source": "iso25010",
            "text": "Test req", "refs": []}]}]}
    (compiled / "security.json").write_text(json.dumps(data))

    loader_calls: list = []
    sentinel_overrides = {"S-CON-1": {"floorMajor": 9.0}}

    def _fake_loader(project_root):
        loader_calls.append(project_root)
        return sentinel_overrides

    with patch(
        "quodeq.analysis.prompts.builder.load_project_overrides",
        side_effect=AssertionError("the concrete loader must not be called"),
    ), patch(
        "quodeq.analysis.prompts.builder.render_all_standards",
        wraps=render_all_standards,
    ) as spy_render:
        build_consolidated_prompt(
            dimensions=["security"],
            context=PromptContext(
                language="python", repo_name="test", date_str="2026-03-22",
                dimension="consolidated", source_file_count=20,
                dimensions_data=_sample_dimensions(),
                standards_dir=tmp_path,
                project_root=tmp_path,
                overrides_loader=_fake_loader,
            ),
        )
    assert loader_calls == [tmp_path]
    assert spy_render.call_args.kwargs["overrides"] is sentinel_overrides
