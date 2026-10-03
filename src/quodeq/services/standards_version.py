"""Fingerprint of the standards a rescore reads, for the score-cache version hashes.

A rescore resolves every finding's principle against the compiled standards
(``evidence_rescore.standard_dirs``) and quarantines what no longer maps, so
an edited or added standard changes the rows ``run_scalars`` would hold. The
version hashes in ``score_cache`` fold this fingerprint in; without it an
edit applied only on the next full rescore.

Stat-based on purpose: a request computes it once per project, and the nine
compiled files plus the project's threshold overrides are only ``stat``-ed,
never read, so it costs no I/O the perf budgets count. A reinstall that
rewrites mtimes makes every run stale once, which recomputes identical rows.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quodeq.core.standards.overrides import OVERRIDES_RELPATH
from quodeq.services._fs_project_primitives import local_repo_root
from quodeq.services.evidence_rescore import standard_dirs
from quodeq.shared.utils import TEXT_ENCODING

_UNSET = object()


def _stat_entry(path: Path) -> list[int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return [stat.st_size, stat.st_mtime_ns]


def standards_fingerprint(project_dir: Path, *, compiled_dir: Path | None | object = _UNSET) -> str:
    """Hash of the compiled standards and *project_dir*'s threshold overrides.

    *project_dir* is ``<reports root>/<project>``; the overrides file lives in
    the project's local clone (``repository_info.json`` ``path``), and a
    project without one contributes no overrides. *compiled_dir* defaults to
    the directory a rescore resolves.
    """
    if compiled_dir is _UNSET:
        compiled_dir, _ = standard_dirs()
    compiled: dict[str, list[int]] = {}
    if isinstance(compiled_dir, Path) and compiled_dir.is_dir():
        for path in sorted(compiled_dir.glob("*.json")):
            entry = _stat_entry(path)
            if entry is not None:
                compiled[path.name] = entry
    repo_root = local_repo_root(project_dir.parent, project_dir.name)
    overrides = _stat_entry(repo_root / OVERRIDES_RELPATH) if repo_root else None
    payload = json.dumps({"compiled": compiled, "overrides": overrides}, sort_keys=True)
    return hashlib.sha256(payload.encode(TEXT_ENCODING)).hexdigest()
