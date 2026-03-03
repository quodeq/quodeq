from __future__ import annotations

from pathlib import Path

from codecompass.v2.engine.finding import Finding


def build_judge_context(
    findings: list[Finding],
    practices: dict,
    analysis_md: str,
    dimensions_config: dict,
    standards_dir: Path | None = None,
    src_dir: Path | None = None,
) -> str:
    """Assemble the full context string for the LLM judge."""
    sections: list[str] = []

    # Section 1: Detector findings grouped by dimension
    sections.append(_format_findings(findings))

    # Section 2: Practices with bad/good examples
    sections.append(_format_practices(practices))

    # Section 3: Analysis guidance
    if analysis_md:
        sections.append(f"## Analysis Guidance\n\n{analysis_md}")

    # Section 4: ISO 25010 dimension requirements
    sections.append(_format_dimensions(dimensions_config, standards_dir))

    # Section 5: Code snippets around finding locations
    if src_dir and findings:
        snippet_section = _format_code_snippets(findings, src_dir)
        if snippet_section:
            sections.append(snippet_section)

    return "\n\n---\n\n".join(sections)


def _format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "## Detector Findings\n\nNo findings from automated detectors."

    by_dimension: dict[str, list[Finding]] = {}
    for f in findings:
        by_dimension.setdefault(f.dimension, []).append(f)

    lines = ["## Detector Findings\n"]
    for dim, dim_findings in sorted(by_dimension.items()):
        lines.append(f"### {dim.title()}")
        for f in dim_findings:
            cwe = f" (CWE-{f.cwe})" if f.cwe else ""
            snippet = f": `{f.snippet}`" if f.snippet else ""
            lines.append(f"- **{f.label}**{cwe} — `{f.file}`:{f.line or '?'}{snippet}")
        lines.append("")

    return "\n".join(lines)


def _format_practices(practices: dict) -> str:
    practice_list = practices.get("practices", [])
    if not practice_list:
        return "## Practices\n\nNo practices defined."

    lines = ["## Practices\n"]
    for p in practice_list:
        lines.append(f"### {p['id']}: {p['title']}")
        lines.append(f"- **Dimension:** {p['dimension']} | **Severity:** {p['severity']} | **CWE:** {p.get('cwe', 'N/A')}")
        lines.append(f"- **Bad:**\n```\n{p['bad']}\n```")
        lines.append(f"- **Good:**\n```\n{p['good']}\n```")
        lines.append(f"- **Why:** {p.get('explanation', '')}")
        lines.append("")

    return "\n".join(lines)


def _format_dimensions(dimensions_config: dict, standards_dir: Path | None) -> str:
    applies = dimensions_config.get("applies", [])
    if not applies:
        return "## Dimensions\n\nNo dimensions configured."

    lines = ["## Dimensions\n"]
    for dim in applies:
        iso = dim.get("iso_25010", "")
        source = dim.get("source", "")
        weight = dim.get("weight", 1.0)
        lines.append(f"- **{dim['id']}** (weight: {weight}){f' — {iso}' if iso else ''}{f' [{source}]' if source else ''}")

        # Load standards requirements if available
        if standards_dir:
            std_file = standards_dir / "iso25010" / f"{dim['id']}.json"
            if std_file.exists():
                import json
                std = json.loads(std_file.read_text())
                sub_chars = std.get("sub_characteristics", [])
                if sub_chars and isinstance(sub_chars[0], dict):
                    for sc in sub_chars:
                        lines.append(f"  **{sc['name']}**:")
                        for req in sc.get("requirements", []):
                            lines.append(f"    - {req['id']}: {req['text']}")
                else:
                    for req in std.get("requirements", []):
                        lines.append(f"  - {req.get('id', '')}: {req.get('text', '')}")

    return "\n".join(lines)


def _format_code_snippets(findings: list[Finding], src_dir: Path) -> str:
    """Extract code snippets around finding locations."""
    seen: set[tuple[str, int]] = set()
    lines = ["## Code Context\n"]
    count = 0

    for f in findings:
        if not f.file or not f.line:
            continue
        key = (f.file, f.line)
        if key in seen:
            continue
        seen.add(key)

        filepath = Path(f.file) if Path(f.file).is_absolute() else src_dir / f.file
        if not filepath.exists():
            continue

        try:
            source_lines = filepath.read_text().splitlines()
            start = max(0, f.line - 3)
            end = min(len(source_lines), f.line + 3)
            snippet = "\n".join(
                f"{'>' if i + 1 == f.line else ' '} {i + 1:4d} | {source_lines[i]}"
                for i in range(start, end)
            )
            lines.append(f"### `{f.file}` line {f.line} ({f.label})")
            lines.append(f"```\n{snippet}\n```\n")
            count += 1
        except (OSError, UnicodeDecodeError):
            continue

        if count >= 20:
            break

    return "\n".join(lines) if count > 0 else ""
