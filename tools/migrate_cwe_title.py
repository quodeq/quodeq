#!/usr/bin/env python3
"""One-time migration: set 'title' to the CWE name for violations/compliance.

Entries that have a 'cwe' ID but an empty or missing 'title' get their title
filled in from the compiled standards CWE name lookup
(e.g. CWE-306 → "Missing Authentication for Critical Function").

Usage:
    python3 tools/migrate_cwe_title.py                          # dry-run
    python3 tools/migrate_cwe_title.py --apply                  # write changes
    python3 tools/migrate_cwe_title.py --dir /path/to/evals     # custom dir
    python3 tools/migrate_cwe_title.py --standards standards/compiled
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Standalone script — add src/ to sys.path so quodeq imports resolve
# without requiring the package to be installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quodeq.shared.utils import TEXT_ENCODING as _TEXT_ENCODING


def _build_cwe_name_lookup(compiled_dir: Path) -> dict[int, str]:
    """Build CWE ID -> name from all compiled standards files."""
    lookup: dict[int, str] = {}
    for f in compiled_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding=_TEXT_ENCODING))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"  SKIP  cannot read {f}: {exc}")
            continue
        if not isinstance(data, dict):
            print(f"  SKIP  unexpected payload type in {f}: {type(data).__name__}")
            continue
        for principle in data.get("principles", []):
            for cwe in principle.get("cwes", []):
                cid = cwe.get("id")
                name = cwe.get("name", "")
                if isinstance(cid, int) and name and cid not in lookup:
                    lookup[cid] = name
    return lookup


def _patch_entries(entries: list[dict], cwe_names: dict[int, str]) -> int:
    """Set title to CWE name where title is empty/missing and cwe is present."""
    patched = 0
    for entry in entries:
        if entry.get("title"):
            continue
        cwe = entry.get("cwe")
        if not isinstance(cwe, int):
            continue
        name = cwe_names.get(cwe)
        if name:
            entry["title"] = name
            patched += 1
    return patched


def migrate_file(path: Path, cwe_names: dict[int, str], apply: bool) -> tuple[int, int]:
    """Patch a single evaluation JSON file, filling empty titles from CWE names.

    Returns (violations_patched, compliance_patched).

    Note: this one-shot migration script intentionally mixes file I/O with
    transformation logic — strict layering is not warranted for tooling
    that runs once and is kept only for auditability.
    """
    try:
        data = json.loads(path.read_text(encoding=_TEXT_ENCODING))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"  SKIP  cannot read {path}: {exc}")
        return 0, 0
    if not isinstance(data, dict):
        print(f"  SKIP  unexpected payload type in {path}: {type(data).__name__}")
        return 0, 0
    v_count = _patch_entries(data.get("violations", []), cwe_names)
    c_count = _patch_entries(data.get("compliance", []), cwe_names)

    if apply and (v_count or c_count):
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding=_TEXT_ENCODING)
        except OSError as exc:
            print(f"  ERROR writing {path}: {exc}")

    return v_count, c_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill CWE names into evaluation JSON titles")
    parser.add_argument("--dir", default="evaluations", help="Evaluations root directory")
    parser.add_argument("--standards", default="standards/compiled", help="Compiled standards directory")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()

    root = Path(args.dir)
    compiled_dir = Path(args.standards)

    if not root.exists():
        print(f"Directory not found: {root}")
        sys.exit(1)
    if not compiled_dir.exists():
        print(f"Compiled standards not found: {compiled_dir}")
        sys.exit(1)

    cwe_names = _build_cwe_name_lookup(compiled_dir)
    print(f"Loaded {len(cwe_names)} CWE names from {compiled_dir}")

    eval_files = sorted(root.rglob("evaluation/*.json"))
    if not eval_files:
        print("No evaluation/*.json files found.")
        sys.exit(0)

    total_v = total_c = files_changed = 0

    for path in eval_files:
        v, c = migrate_file(path, cwe_names, args.apply)
        rel = path.relative_to(root)
        if v or c:
            files_changed += 1
            total_v += v
            total_c += c
            print(f"  {'updated' if args.apply else 'would update'} {rel}: +{v} violation titles, +{c} compliance titles")
        else:
            print(f"  ok       {rel}  (nothing to patch)")

    mode = "Applied" if args.apply else "Dry-run"
    print(f"\n{mode}: {files_changed} files, {total_v} violations, {total_c} compliance entries")
    if not args.apply and (total_v or total_c):
        print("Run with --apply to write changes.")


if __name__ == "__main__":
    main()
