from quodeq.resolver.models import (
    FindingInput,
    FunctionInfo,
    Location,
    Manifest,
)
from quodeq.verifier.prompt import (
    SYSTEM_PROMPT_V7_2,
    render_user_prompt,
)


def _example_manifest() -> Manifest:
    return Manifest(
        target_file="src/quodeq/api/app.py",
        target_line=6,
        target_file_role="composition_root",
        referenced_symbol="FilesystemActionProvider",
        referenced_symbol_defined_at=Location("src/quodeq/services/filesystem.py", 39),
        referenced_symbol_bases=["FsEvaluationMixin", "FsToolingMixin", "ActionProvider"],
        abstraction="ActionProvider",
        abstraction_defined_at=Location("src/quodeq/services/base.py", 134),
        abstraction_kind="Protocol",
        abstraction_implementations_prod=1,
        abstraction_implementations_test_stubs=3,
        abstraction_used_as_parameter_type_in=[Location("src/quodeq/api/app.py", 75)],
        target_enclosing_function=FunctionInfo(
            name="_default_provider",
            signature="def _default_provider() -> ActionProvider",
            file="src/quodeq/api/app.py",
            line=4,
            return_type="ActionProvider",
            parameters=[],
            lazy_imports_inside_body=True,
        ),
        target_parent_function=FunctionInfo(
            name="create_app",
            signature="def create_app(provider: ActionProvider | None = None) -> Flask",
            file="src/quodeq/api/app.py",
            line=10,
            return_type="Flask",
            parameters=["provider"],
            lazy_imports_inside_body=False,
        ),
        target_parent_seam_at=Location("src/quodeq/api/app.py", 11),
        target_parent_seam_pattern="provider = provider or _default_provider()",
        enclosing_function_called_from=[Location("src/quodeq/api/app.py", 11)],
    )


def test_system_prompt_is_constant_and_nonempty():
    assert isinstance(SYSTEM_PROMPT_V7_2, str)
    assert len(SYSTEM_PROMPT_V7_2) > 200
    # Contains the worked example markers
    assert "default_implementation" in SYSTEM_PROMPT_V7_2
    assert "MANIFEST" in SYSTEM_PROMPT_V7_2


def test_render_user_prompt_includes_finding(tmp_path):
    finding = FindingInput(
        file="src/quodeq/api/app.py",
        line=6,
        category="flexibility/adaptability",
        severity="major",
        description="hardcoded provider",
    )
    text = render_user_prompt(_example_manifest(), finding, project_root=tmp_path)
    assert "src/quodeq/api/app.py:6" in text or "src/quodeq/api/app.py" in text
    assert "flexibility/adaptability" in text or "claim" in text.lower()


def test_render_user_prompt_includes_manifest_keys(tmp_path):
    finding = FindingInput(
        file="src/quodeq/api/app.py",
        line=6,
        category="flexibility/adaptability",
    )
    text = render_user_prompt(_example_manifest(), finding, project_root=tmp_path)
    assert "composition_root" in text
    assert "FilesystemActionProvider" in text
    assert "ActionProvider" in text
    assert "Protocol" in text


def test_render_user_prompt_includes_seam(tmp_path):
    finding = FindingInput(
        file="src/quodeq/api/app.py",
        line=6,
        category="flexibility/adaptability",
    )
    text = render_user_prompt(_example_manifest(), finding, project_root=tmp_path)
    assert "provider = provider or _default_provider()" in text or "or _default_provider()" in text


def test_render_user_prompt_includes_evidence_block_headers(tmp_path):
    # Write the file the manifest references so the evidence renderer can read it.
    target = tmp_path / "src" / "quodeq" / "api" / "app.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(f"line {i}" for i in range(1, 20)) + "\n", encoding="utf-8")
    finding = FindingInput(
        file="src/quodeq/api/app.py",
        line=6,
        category="flexibility/adaptability",
    )
    text = render_user_prompt(_example_manifest(), finding, project_root=tmp_path)
    # Evidence blocks use [<relative-path> L<a>-<b>] headers
    assert "[src/quodeq/api/app.py L" in text


def test_render_user_prompt_includes_checklist(tmp_path):
    finding = FindingInput(
        file="src/quodeq/api/app.py",
        line=6,
        category="flexibility/adaptability",
    )
    text = render_user_prompt(_example_manifest(), finding, project_root=tmp_path)
    assert "Q1." in text or "Q1" in text
    assert "Q5." in text or "Q5" in text


def test_render_user_prompt_includes_findings_request(tmp_path):
    finding = FindingInput(
        file="src/quodeq/api/app.py",
        line=6,
        category="flexibility/adaptability",
    )
    text = render_user_prompt(_example_manifest(), finding, project_root=tmp_path)
    assert "default_implementation" in text
    assert "override_mechanism" in text
    assert "abstraction_in_use" in text
