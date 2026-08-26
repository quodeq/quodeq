"""Writer-epoch salt for the score cache.

Its own leaf module because the two consumers must not import each other: the
version hashes in ``score_cache`` and the ``run_keys`` purge in
``_score_cache_db``.
"""
from __future__ import annotations

# Bumped when the cache *writer* semantics change in a way that could have
# produced bad rows, to invalidate everything written by the prior writer.
# "2": earlier writers persisted in-progress runs' partial scalar sets (e.g. 1
# of 6 dims), which the content-hash version could never invalidate; the
# write-guard now persists only completed runs, and this bump rebuilds the
# stranded partial rows once.
# "3": accumulated / project-summary payloads written before configured-dim
# scoping carried stale dimensions (e.g. clean-architecture) that the project
# no longer evaluates; the run-fingerprint could never invalidate them, so this
# bump rebuilds them once against the latest run's configured-dimension set.
# "4": earlier writers persisted in-progress runs' PARTIAL run_keys sets (the
# per-run version path had no completeness gate), which load_run_keys froze
# forever; the gate now persists only terminal runs, and this bump purges the
# non-version-keyed run_keys table once so stranded partial snapshots rebuild.
# "5": dismiss/delete rescoring switched basis from the legacy report-JSON
# formula to the run's own evidence jsonl (services/evidence_rescore), so
# scores cached by the prior writer differ for the SAME suppression state and
# params; this bump rebuilds them on the evidence basis once.
# "6": three scoring read paths built their run-dimension fetcher without the
# staleness guards (in-progress bypass + eval-file-count validation), so a
# request landing mid-run could freeze a partial dim list in the process LRU;
# later writes built from it persisted half-rescored accumulated payloads and
# partial scalar sets whose version hash can never self-invalidate. The guards
# now live in the shared fetcher and the accumulated writer refuses
# partial-coverage payloads; this bump rebuilds rows the prior writer may have
# poisoned.
CACHE_WRITER_EPOCH = "6"
