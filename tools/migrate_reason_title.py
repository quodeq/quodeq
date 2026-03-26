#!/usr/bin/env python3
"""One-time migration: clean 'reason' field in evaluation JSONs.

Old evaluation JSONs may have the principle name baked into the reason as a
prefix ("Principle — explanation"). This script strips that prefix so the
reason field contains only the LLM explanation. The principle is already
shown separately in the UI header.

For entries where the prefix differs from the principle (i.e., it's a practice
title), the prefix is moved to a 'title' field so the UI can render it bold.

Usage:
    python3 tools/migrate_reason_title.py                          # dry-run
    python3 tools/migrate_reason_title.py --apply                  # write changes
    python3 tools/migrate_reason_title.py --dir /path/to/evals     # custom dir
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SEPARATORS = [" \u2014 "]  # em-dash; previous list had a duplicate entry


def _find_first_sep(text: str) -> tuple[int, str] | tuple[None, None]:
    """Find the position and value of the first separator in text."""
    best_idx = None
    best_sep = None
    for sep in SEPARATORS:
        idx = text.find(sep)
        if idx > 0 and (best_idx is None or idx < best_idx):
            best_idx = idx
            best_sep = sep
    return best_idx, best_sep


def migrate_entry(entry: dict) -> bool:
    """Migrate a single violation/compliance entry. Returns True if changed."""
    reason = entry.get("reason", "")
    if not reason:
        return False

    # Already migrated — has a title key (even if empty). Skip.
    if "title" in entry:
        return False

    principle = entry.get("principle", "")

    # Reason starts with "Principle — ..." — strip the prefix.
    idx, sep = _find_first_sep(reason)
    if idx is not None and sep is not None:
        prefix = reason[:idx]
        explanation = reason[idx + len(sep):]

        if prefix == principle:
            # Principle prefix — just strip it, no title needed.
            entry["reason"] = explanation
            entry["title"] = ""
            return True
        else:
            # Practice title prefix — move to title field.
            entry["title"] = prefix
            entry["reason"] = explanation
            return True

    # No separator found — set empty title.
    entry["title"] = ""
    return True


def migrate_file(path: Path, apply: bool) -> tuple[int, int]:
    """Migrate a single evaluation JSON. Returns (violations_updated, compliance_updated)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"  SKIP  cannot read {path}: {exc}")
        return 0, 0
    v_count = sum(1 for entry in data.get("violations", []) if migrate_entry(entry))
    c_count = sum(1 for entry in data.get("compliance", []) if migrate_entry(entry))

    if apply and (v_count or c_count):
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"  ERROR writing {path}: {exc}")

    return v_count, c_count


def main():
    parser = argparse.ArgumentParser(description="Migrate reason field in evaluation JSONs")
    parser.add_argument("--dir", default="evaluations", help="Evaluations root directory")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()
    if not args.dir or not args.dir.strip():
        print("Error: --dir must not be empty", file=sys.stderr)
        sys.exit(1)

    try:
        root = Path(args.dir)
        if not root.exists():
            print(f"Directory not found: {root}")
            sys.exit(1)

        eval_files = list(root.rglob("evaluation/*.json"))
        if not eval_files:
            print("No evaluation/*.json files found.")
            sys.exit(0)

        total_v = 0
        total_c = 0
        files_changed = 0

        for path in sorted(eval_files):
            try:
                v, c = migrate_file(path, args.apply)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"  ERROR processing {path}: {exc}")
                continue
            if v or c:
                files_changed += 1
                total_v += v
                total_c += c
                rel = path.relative_to(root)
                print(f"  {'updated' if args.apply else 'would update'} {rel}: {v} violations, {c} compliance")

        mode = "Applied" if args.apply else "Dry-run"
        print(f"\n{mode}: {files_changed} files, {total_v} violations, {total_c} compliance entries")
        if not args.apply and (total_v or total_c):
            print("Run with --apply to write changes.")
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
