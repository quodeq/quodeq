"""Finding-detail lookup from a run's legacy ``evaluation/<dim>.json`` files.

The SQL twin is ``quodeq.data.sqlite.findings_queries.read_finding_details``
(the ``findings`` table); this reader serves runs that pre-date the
event-log scoring engine and so never produced that table.
services/dismissed.py used to walk and parse these files inline.
"""
from __future__ import annotations

import json
from pathlib import Path


def read_finding_details_from_json_eval(
    run_dir: Path, keys: set[tuple],
) -> dict[tuple, dict]:
    """Return finding-detail dicts for the ``(requirement, file, line)``
    *keys* found in *run_dir*'s ``evaluation/*.json`` files.

    Keys not present are simply absent from the result; the first file
    mentioning a key wins. ``dimension`` comes from the filename so the
    entry stays linked to its standard. Unreadable files are skipped.
    """
    eval_dir = run_dir / "evaluation"
    if not eval_dir.is_dir():
        return {}
    out: dict[tuple, dict] = {}
    for path in eval_dir.iterdir():
        if path.suffix != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        dimension = path.stem
        for v in (data.get("violations") or []):
            req = str(v.get("req") or "")
            file = str(v.get("file") or "")
            try:
                line = int(v.get("line") or 0)
            except (TypeError, ValueError):
                line = 0
            key = (req, file, line)
            if key not in keys or key in out:
                continue
            out[key] = {
                "req": req, "file": file, "line": line,
                "dimension": dimension, "principle": v.get("principle") or "",
                "severity": v.get("severity") or "", "title": v.get("title") or "",
                "reason": v.get("reason") or "", "snippet": v.get("snippet") or "",
                "context": v.get("context") or "", "scope": v.get("scope") or "",
                "endLine": int(v.get("end_line") or v.get("endLine") or 0),
                "reqRefs": v.get("req_refs") or v.get("reqRefs") or [],
            }
    return out
