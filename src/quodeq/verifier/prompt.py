"""v7.2 prompt renderer.

The system prompt is a module-level constant -- same for every finding, cached
once by Ollama. The user prompt is rendered per-finding from a Manifest and a
FindingInput.

Reference: memory/project_enricher_fixture_di_default.md (canonical fixture
documenting the v7.2 template and the structured-findings format).
"""

from __future__ import annotations

from pathlib import Path

from quodeq.resolver.models import FindingInput, Location, Manifest


SYSTEM_PROMPT_V7_2 = """You verify static-analysis findings using ONLY the prompt's evidence.

RULES:
- Don't invent files, lines, or symbols.
- Citations: a visible "L<N>" line, "MANIFEST", or null.
- If unanswerable, return "unknown" with cite=null.
- Each `findings` value is concrete or null; cite required when non-null.
- Do NOT emit a verdict.

Output exactly one JSON object with this shape (example for a different case):
{
  "checklist": {
    "Q1": {"answer": "yes", "cite": "MANIFEST"},
    "Q2": {"answer": "yes", "cite": "services/notify.py:8"},
    "Q3": {"answer": "yes", "cite": "services/notify.py:15"},
    "Q4": {"answer": "yes", "cite": "MANIFEST"},
    "Q5": {"answer": "yes", "cite": "services/notify.py:21"}
  },
  "findings": {
    "default_implementation": {"value": "SMTPNotifier", "cite": "services/notify.py:8"},
    "override_mechanism": {"value": "impl param, 'impl or _default_notifier()'", "cite": "services/notify.py:21"},
    "abstraction_in_use": {"value": "Notifier", "cite": "MANIFEST"}
  },
  "confidence": 0.95,
  "evidence_summary": "SMTPNotifier is default; make_notifier accepts any Notifier via impl."
}
"""


def render_user_prompt(
    manifest: Manifest,
    finding: FindingInput,
    project_root: Path | None = None,
) -> str:
    """Render the per-finding user prompt from a manifest.

    `project_root` resolves the manifest's relative file paths to disk when
    reading evidence windows. If None, paths are used as-is (treated as
    absolute or CWD-relative).
    """
    parts: list[str] = []

    parts.append("### FINDING")
    parts.append(f"location={manifest.target_file}:{manifest.target_line}")
    if finding.description:
        parts.append(f"claim: {finding.description}")
    else:
        parts.append(
            "claim: This finding asserts the import at the cited line creates a "
            "hardcoded dependency requiring modification to swap out."
        )

    parts.append("")
    parts.append("### MANIFEST")
    parts.append(_render_manifest_block(manifest))

    parts.append("")
    parts.append(_render_evidence_blocks(manifest, project_root))

    parts.append("")
    parts.append("### CHECKLIST")
    parts.append("Q1. Is target.role == \"composition_root\"?")
    parts.append("Q2. Is the cited line lexically nested inside a `def` shown earlier in the same file?")
    parts.append("Q3. Does the parent function accept the abstraction as a parameter?")
    parts.append("Q4. Is the imported concrete class a subtype of a Protocol/ABC per the evidence?")
    parts.append("Q5. Does the parent use a \"param or factory()\" seam at a line shown above?")

    parts.append("")
    parts.append("### FINDINGS REQUEST")
    parts.append("Extract these concrete facts from the evidence. Each must include a citation.")
    parts.append("- default_implementation: the concrete class instantiated by the default code path.")
    parts.append(
        "- override_mechanism: a short phrase describing how a caller can supply a "
        "different implementation (parameter name + seam pattern)."
    )
    parts.append("- abstraction_in_use: the Protocol or ABC type that callers can substitute.")

    return "\n".join(parts)


def _render_manifest_block(m: Manifest) -> str:
    lines: list[str] = []
    lines.append(f"target={m.target_file}:{m.target_line}  role={m.target_file_role}")
    if m.referenced_symbol:
        line = f"ref_symbol={m.referenced_symbol}"
        if m.referenced_symbol_defined_at:
            line += f"  def_at={m.referenced_symbol_defined_at}"
        lines.append(line)
    if m.abstraction:
        line = f"abstraction={m.abstraction}"
        if m.abstraction_defined_at:
            line += f"  def_at={m.abstraction_defined_at}"
        if m.abstraction_kind:
            line += f"  kind={m.abstraction_kind}"
        lines.append(line)
        lines.append(
            f"impls={m.abstraction_implementations_prod} prod + "
            f"{m.abstraction_implementations_test_stubs} test_stubs"
        )
    if m.abstraction_used_as_parameter_type_in:
        users = ", ".join(str(loc) for loc in m.abstraction_used_as_parameter_type_in)
        lines.append(f"param_use={users}")
    if m.target_parent_seam_at:
        seam_line = f"seam={m.target_parent_seam_at}"
        if m.target_parent_seam_pattern:
            seam_line += f"  pattern={m.target_parent_seam_pattern!r}"
        lines.append(seam_line)
    return "\n".join(lines)


def _render_evidence_blocks(m: Manifest, project_root: Path | None) -> str:
    """Render evidence blocks for any locations referenced by the manifest.

    Uses the manifest's relative file paths in headers (so model citations
    will match) and reads file bytes from `<project_root>/<relative_path>`
    when project_root is provided. Falls back to using paths as-is otherwise.
    """
    blocks: list[str] = []
    seen: set[tuple[str, int, int]] = set()

    def resolve(rel_path: str) -> Path:
        if project_root is not None:
            return project_root / rel_path
        return Path(rel_path)

    def window(loc: Location, around: int = 2) -> None:
        path = resolve(loc.file)
        if not path.exists():
            return
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, loc.line - around)
        end = min(len(text), loc.line + around)
        key = (loc.file, start, end)
        if key in seen:
            return
        seen.add(key)
        # Use the manifest's relative path in the header so model citations
        # like "src/foo/bar.py:90" line up with what's visible in the prompt.
        header = f"[{loc.file} L{start}-{end}]"
        rendered = [header]
        for i in range(start, end + 1):
            rendered.append(f"L{i} | {text[i - 1]}")
        blocks.append("\n".join(rendered))

    if m.abstraction_defined_at:
        window(m.abstraction_defined_at, around=3)
    if m.referenced_symbol_defined_at:
        window(m.referenced_symbol_defined_at, around=1)
    if m.target_enclosing_function:
        window(
            Location(m.target_enclosing_function.file, m.target_enclosing_function.line),
            around=4,
        )
    if m.target_parent_function:
        window(
            Location(m.target_parent_function.file, m.target_parent_function.line),
            around=3,
        )
    if m.target_parent_seam_at:
        window(m.target_parent_seam_at, around=0)

    return "\n\n".join(blocks)
