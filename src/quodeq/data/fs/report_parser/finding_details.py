"""Finding-detail lookup from a run's legacy ``evaluation/<dim>.json`` files.

The SQL twin is ``quodeq.data.sqlite.findings_queries.read_finding_details``
(the ``findings`` table); this reader serves runs that pre-date the
event-log scoring engine and so never produced that table.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from quodeq.core.finding_identity import coerce_line, finding_dismiss_keys
from quodeq.shared.constants import JSON_SUFFIX


def iter_eval_reports(eval_dir: Path, *, skip_corrupt: bool = False) -> Iterator[tuple[str, dict]]:
    """Yield ``(dimension, data)`` for every ``<dim>.json`` file in
    *eval_dir*, in filename order. ``dimension`` is the filename stem.

    Malformed JSON propagates by default -- a corrupt evaluation report is a
    bug in the run, not something callers should silently skip over.
    ``skip_corrupt=True`` instead skips just that one file and continues
    with the rest, for callers (e.g. the assistant's finding-identity index)
    that must keep serving every healthy dimension even when one report is
    truncated or corrupt -- a known failure mode of deadline-cut runs.
    """
    for path in sorted(eval_dir.glob("*.json")):
        if skip_corrupt:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            yield path.stem, data
        else:
            yield path.stem, json.loads(path.read_text(encoding="utf-8"))


def iter_readable_eval_reports(run_dir: Path) -> Iterator[tuple[str, object]]:
    """Yield ``(dimension, data)`` for each readable ``evaluation/<dim>.json`` in *run_dir*.

    Directory order, not sorted (unlike ``iter_eval_reports``). A file that
    cannot be read or is not valid JSON is skipped; ``data`` is whatever the
    JSON holds, so callers that need an object check for one. No
    ``evaluation/`` directory yields nothing.
    """
    eval_dir = run_dir / "evaluation"
    if not eval_dir.is_dir():
        return
    for path in eval_dir.iterdir():
        if path.suffix != JSON_SUFFIX:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        yield path.stem, data


def read_eval_report(eval_dir: Path, dimension: str) -> dict | None:
    """Read the single ``<dimension>.json`` report from *eval_dir*, or
    ``None`` if it doesn't exist. Malformed JSON propagates."""
    path = eval_dir / f"{dimension}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_finding_details_from_json_eval(
    run_dir: Path, keys: set[tuple],
) -> dict[tuple, dict]:
    """Return finding-detail dicts for the dismiss *keys* found in
    *run_dir*'s ``evaluation/*.json`` files.

    A key is ``(req, file, line)`` or ``(req, file, snippet fingerprint)``
    and a violation matches on any identity a dismissal of it may have been
    recorded under (``finding_dismiss_keys``), the same rule as the SQL twin
    in ``findings_queries``. Keys not present are simply absent from the
    result; the first file mentioning a key wins. ``dimension`` comes from
    the filename so the entry stays linked to its standard. Unreadable files
    are skipped.
    """
    wanted = set(keys)
    out: dict[tuple, dict] = {}
    for dimension, data in iter_readable_eval_reports(run_dir):
        for v in (data.get("violations") or []):
            req = str(v.get("req") or "")
            file = str(v.get("file") or "")
            line = coerce_line(v.get("line") or 0)
            hits = finding_dismiss_keys(
                req=req, principle=v.get("principle") or v.get("practiceId"),
                file=file, line=line, snippet=v.get("snippet"),
            ) & wanted
            hits.difference_update(out)
            if not hits:
                continue
            detail = {
                "req": req, "file": file, "line": line,
                "dimension": dimension, "principle": v.get("principle") or "",
                "severity": v.get("severity") or "", "title": v.get("title") or "",
                "reason": v.get("reason") or "", "snippet": v.get("snippet") or "",
                "context": v.get("context") or "", "scope": v.get("scope") or "",
                "endLine": int(v.get("end_line") or v.get("endLine") or 0),
                "reqRefs": v.get("req_refs") or v.get("reqRefs") or [],
            }
            for key in hits:
                out[key] = detail
    return out
