#!/usr/bin/env python3
"""Resolve per-language practices with compiled standards data.

Usage:
    python3 tools/resolve_practices.py --lang python
    python3 tools/resolve_practices.py --all
    python3 tools/resolve_practices.py --validate
"""
import argparse
import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
COMPILED_DIR = repo_root / "v2" / "standards" / "compiled"
EVALUATORS_DIR = repo_root / "v2" / "evaluators"


def load_compiled_standards(compiled_dir: Path) -> dict[str, dict]:
    """Load all compiled dimension files into a dict keyed by dimension id."""
    standards = {}
    for f in compiled_dir.glob("*.json"):
        data = json.loads(f.read_text())
        standards[data["id"]] = data
    return standards


def resolve_practice(practice: dict, compiled: dict[str, dict]) -> tuple[dict, list[str]]:
    """Resolve a single practice against compiled standards.

    Returns (resolved_practice, warnings).
    """
    warnings: list[str] = []
    resolved = dict(practice)  # shallow copy
    pid = practice["id"]
    dimension = practice.get("dimension", "")
    principle = practice.get("principle", "")
    raw_cwe = practice.get("cwe")
    cwe_id = raw_cwe["id"] if isinstance(raw_cwe, dict) else raw_cwe

    if dimension not in compiled:
        warnings.append(f"{pid}: dimension '{dimension}' not in compiled standards")
        return resolved, warnings

    dim_data = compiled[dimension]

    # Find the CWE in the declared principle
    cwe_entry = None
    found_in_principle = None
    for p in dim_data.get("principles", []):
        for cwe in p.get("cwes", []):
            if cwe["id"] == cwe_id:
                if p["name"] == principle:
                    cwe_entry = cwe
                    found_in_principle = p["name"]
                elif cwe_entry is None:
                    # Found under a different principle
                    cwe_entry = cwe
                    found_in_principle = p["name"]

    if cwe_entry is None:
        warnings.append(f"{pid}: CWE-{cwe_id} not found in compiled {dimension}")
        resolved["cwe"] = {"id": cwe_id, "name": f"CWE-{cwe_id}"}
        resolved["standards"] = []
        return resolved, warnings

    if found_in_principle != principle:
        warnings.append(
            f"{pid}: declares principle '{principle}' but CWE-{cwe_id} "
            f"found under '{found_in_principle}'"
        )

    resolved["cwe"] = {"id": cwe_entry["id"], "name": cwe_entry["name"]}
    resolved["standards"] = cwe_entry["refs"]

    return resolved, warnings


def resolve_evaluator(lang_dir: Path, compiled: dict[str, dict], validate_only: bool = False) -> tuple[dict | None, list[str]]:
    """Resolve all practices for one evaluator.

    Returns (resolved_data, all_warnings). resolved_data is None in validate mode.
    """
    practices_file = lang_dir / "knowledge" / "practices.json"
    if not practices_file.exists():
        return None, [f"{lang_dir.name}: no practices.json"]

    data = json.loads(practices_file.read_text())
    all_warnings: list[str] = []
    resolved_practices = []

    for practice in data.get("practices", []):
        resolved, warnings = resolve_practice(practice, compiled)
        resolved_practices.append(resolved)
        all_warnings.extend(warnings)

    if validate_only:
        return None, all_warnings

    resolved_data = dict(data)
    resolved_data["practices"] = resolved_practices
    return resolved_data, all_warnings


def main():
    parser = argparse.ArgumentParser(description="Resolve practices with compiled standards")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--lang", "-l", help="Resolve one language (e.g. python)")
    group.add_argument("--all", "-a", action="store_true", help="Resolve all evaluators")
    group.add_argument("--validate", "-v", action="store_true", help="Validate only, don't write")
    parser.add_argument("--compiled-dir", type=Path, default=COMPILED_DIR)
    parser.add_argument("--evaluators-dir", type=Path, default=EVALUATORS_DIR)
    args = parser.parse_args()

    compiled = load_compiled_standards(args.compiled_dir)
    if not compiled:
        print(f"Error: no compiled standards in {args.compiled_dir}", file=sys.stderr)
        sys.exit(1)

    if args.validate:
        langs = sorted(d.name for d in args.evaluators_dir.iterdir()
                       if d.is_dir() and not d.name.startswith("_"))
    elif args.all:
        langs = sorted(d.name for d in args.evaluators_dir.iterdir()
                       if d.is_dir() and not d.name.startswith("_"))
    else:
        langs = [args.lang]

    any_warnings = False
    for lang in langs:
        lang_dir = args.evaluators_dir / lang
        resolved_data, warnings = resolve_evaluator(
            lang_dir, compiled, validate_only=args.validate
        )

        for w in warnings:
            print(f"  WARNING: {w}", file=sys.stderr)
            any_warnings = True

        if resolved_data is not None:
            out_file = lang_dir / "knowledge" / "practices.json"
            out_file.write_text(json.dumps(resolved_data, indent=2) + "\n")
            n = len(resolved_data.get("practices", []))
            print(f"  {lang}: {n} practices -> {out_file}")

    if args.validate:
        if any_warnings:
            print("Validation found warnings.", file=sys.stderr)
            sys.exit(1)
        else:
            print("All practices valid.")


if __name__ == "__main__":
    main()
