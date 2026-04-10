#!/usr/bin/env python3
"""One-time migration: backfill CWE IDs into existing evaluation JSONs.

The evidence parser previously ignored the 'cwe' field the AI reported via
the MCP tool. This script re-reads the raw JSONL evidence files (which always
captured it) and patches any missing 'cwe' fields in the stored evaluation
JSONs.

Matching is done on (principle, file, line). If a violation/compliance entry
already has a 'cwe' field it is left untouched.

Usage:
    python3 tools/migrate_cwe.py                          # dry-run
    python3 tools/migrate_cwe.py --apply                  # write changes
    python3 tools/migrate_cwe.py --dir /path/to/evals     # custom dir
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quodeq.shared.utils import TEXT_ENCODING as _TEXT_ENCODING


def _build_cwe_lookup(jsonl_path: Path) -> dict[tuple[str, str, int], int]:
    """Parse a JSONL evidence file into a (principle, file, line) -> cwe_id map."""
    lookup: dict[tuple[str, str, int], int] = {}
    try:
        fh = open(jsonl_path, encoding=_TEXT_ENCODING)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"  SKIP  cannot read {jsonl_path}: {exc}")
        return lookup
    with fh:
        for raw_line in fh:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                print(f"  WARN  malformed JSONL line in {jsonl_path}: {stripped[:80]}")
                continue
            cwe = obj.get("cwe")
            if not isinstance(cwe, int):
                continue
            key = (obj.get("p", ""), obj.get("file", ""), obj.get("line", 0))
            if key not in lookup:
                lookup[key] = cwe
    return lookup


def _patch_entries(entries: list[dict], lookup: dict[tuple[str, str, int], int]) -> int:
    """Add missing 'cwe' to each entry. Returns count of entries patched.

    NOTE: migrate_reason_title.py has a similarly-named concept (migrate_entry)
    but operates on a different field ('reason'/'title') with different logic.
    Extracting a shared helper would over-abstract two unrelated migration passes.
    """
    patched = 0
    for entry in entries:
        if "cwe" in entry:
            continue
        key = (entry.get("principle", ""), entry.get("file", ""), entry.get("line", 0))
        cwe = lookup.get(key)
        if cwe is not None:
            entry["cwe"] = cwe
            patched += 1
    return patched


def migrate_file(eval_path: Path, apply: bool) -> tuple[int, int] | None:
    """Migrate one evaluation JSON using its sibling JSONL. Returns (v_patched, c_patched) or None if no JSONL."""
    dimension = eval_path.stem  # e.g. "security"
    jsonl_path = eval_path.parent.parent / "evidence" / f"{dimension}_evidence.jsonl"
    if not jsonl_path.exists():
        return None

    lookup = _build_cwe_lookup(jsonl_path)
    if not lookup:
        return None

    try:
        data = json.loads(eval_path.read_text(encoding=_TEXT_ENCODING))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"  SKIP  cannot read {eval_path}: {exc}")
        return None
    v_count = _patch_entries(data.get("violations", []), lookup)
    c_count = _patch_entries(data.get("compliance", []), lookup)

    if apply and (v_count or c_count):
        try:
            eval_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding=_TEXT_ENCODING)
        except OSError as exc:
            print(f"  ERROR writing {eval_path}: {exc}")

    return v_count, c_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill CWE IDs into evaluation JSONs")
    parser.add_argument("--dir", default="evaluations", help="Evaluations root directory")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.exists():
        print(f"Directory not found: {root}")
        sys.exit(1)

    eval_files = sorted(root.rglob("evaluation/*.json"))
    if not eval_files:
        print("No evaluation/*.json files found.")
        sys.exit(0)

    total_v = total_c = files_changed = files_skipped = 0

    for path in eval_files:
        result = migrate_file(path, args.apply)
        if result is None:
            files_skipped += 1
            print(f"  skip     {path.relative_to(root)}  (no JSONL found)")
            continue
        v, c = result
        rel = path.relative_to(root)
        if v or c:
            files_changed += 1
            total_v += v
            total_c += c
            print(f"  {'updated' if args.apply else 'would update'} {rel}: +{v} violation CWEs, +{c} compliance CWEs")
        else:
            print(f"  ok       {rel}  (nothing to patch)")

    mode = "Applied" if args.apply else "Dry-run"
    print(f"\n{mode}: {files_changed} files patched, {total_v} violations, {total_c} compliance entries, {files_skipped} skipped")
    if not args.apply and (total_v or total_c):
        print("Run with --apply to write changes.")


if __name__ == "__main__":
    main()
