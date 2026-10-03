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
# per-run version path had no completeness gate), which the persisted run_keys froze
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
# "7": dismiss identity moved from (req, file, line) to (req, file, snippet
# fingerprint) (#1165). Cached run_keys rows hold line keys only, so the
# per-run scoped version could not see a fingerprinted dismissal touch a run;
# this bump purges them so they rebuild with both key shapes.
# "8": run_scalars rows now store each dimension's counts (violations,
# severities, open types) next to its score; rows written by the prior writer
# have none, which History rendered as 0 majors and 0 types for every finished
# run. This bump retires them so they rebuild with the counts.
# "9": run_scalars rows gained a companion table, run_principle_scalars, with
# each dimension's principle scores and grades at the same version. Rows
# written by the prior writer have no principle rows, and a reader cannot tell
# that from a dimension without principles. This bump retires them so every
# cached run carries its principles.
# "10": run_scalars rows gained files_read, which the accumulated walk reads
# to skip coverage-0 stubs when it picks a dimension's winning run from rows.
# A NULL on an older row would read as "unknown, trusted", so they are retired.
# "12": run_scalars rows gained dismissed_count and suppressed_count, which
# the Overview dashboard shows next to each gauge now that it serves the
# selected run from rows. A NULL on an older row would read as "nothing
# hidden" for a run whose findings were suppressed, so they are retired.
CACHE_WRITER_EPOCH = "12"

# Shape of the ``run_keys`` rows, versioned apart from the epoch because the key
# sets are the costly part of a rebuild and most epoch bumps change only score
# rows. Bump it (not only the epoch) when the stored key sets change meaning, as
# epochs "4" (partial snapshots) and "7" (fingerprint keys) did; the table is
# purged once. A cache from epoch "7" or later already holds shape "1".
RUN_KEYS_SHAPE_VERSION = "1"
RUN_KEYS_SHAPE_SINCE_EPOCH = 7
