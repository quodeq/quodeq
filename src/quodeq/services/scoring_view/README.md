# scoring_view — the rules behind every number the dashboard shows

This package owns one question:

> Given the runs we have on disk, **what should each user-facing view
> display, and from which run do its numbers come from?**

Every score, every chip, every history row, every chart bar consults
this package. No view computes its own filter. That's the rule.

---

## Why this package exists

Before centralisation, five places independently decided which runs and
per-dim eval files to surface — `services/accumulated`, `services/dashboard`,
`services/scoring/__init__`, `ui/.../HistoryPage.jsx`,
`services/evaluation_mixin._score_completed_evidence`. Each evolved
opportunistically; every UX bug produced one more filter in one more
file. The user-facing symptom: overview, history, and chart routinely
disagreed about the same run.

The only durable fix is: **one model, one place**.

---

## The model

### Dimensions are the unit, runs are the artifact

A user thinks "what's my security score *now*?", not "show me all the
eval files from run X". Per-dim scoring is the primary axis; runs are
just the bookkeeping for when those scores were produced.

### Run lifecycle vocabulary

A run can be in one of these states (sourced from `status.json` and
the dashboard's external-process detection):

| state | meaning |
|---|---|
| `complete` | Run reached a natural end — every configured dim scored, lifecycle transitioned to DONE. |
| `in_progress` | Currently running. Dims that finish scoring mid-run produce trustworthy eval files immediately. |
| `cancelled` | The run was stopped before natural completion. May be **partial-success** (user-configured time budget honored) or **incomplete** (manual signal, stale-detect, error). The `exit_reason` distinguishes them. |
| `failed` | System error before or during scoring. Eval files written, if any, are not to be trusted. |

### "Successful run" — the canonical definition

A run is **successful** if the data it produced represents the user's
intent. That includes both happy paths:

1. **Naturally completed** — `state == complete`, every dim scored.
2. **Budgeted timeout** — `state == cancelled` AND `exit_reason ∈
   SUCCESSFUL_CANCEL_REASONS` (see `_states.py`). The user said "stop
   at 10 minutes", the run honored that, and stopped with valid data.
   This is *partial-success*: less coverage than complete, but
   intentional and trustworthy.

NOT successful: manual signal cancel, stale-detect (process death),
unhandled exception, token-exhausted error. These produced incomplete
or unreliable data; users shouldn't see them as authoritative scores.

### "Trustable run" — the broader rule, for incremental data salvage

A `cancelled` run that *isn't* a budgeted timeout still has eval files
on disk for the dims it managed to finish. We don't promote those to
the cards/headline (the user didn't intend that stop), but the **next
run's incremental classification** can use them as `analyzed_files`
input — they represent real work the model already did.

A run is trustable iff `state ∈ {complete, in_progress, cancelled}`.
`failed` is excluded — its eval files may be partial-coverage stubs
(`filesRead == 0`) or contain garbage from an interrupted scoring
phase.

### Per-file granularity

Even within a trustable run, individual files may have errored —
typical case: token exhaustion, agent retried twice, gave up. Those
files were *dispatched* (in `queue.taken`) but *no findings landed*
(absent from JSONL). Counting them as analyzed lets the next run
incorrectly skip them. The corrected rule: a file is "analyzed" only
if both the queue dispatched it AND it produced any evidence (or a
signal of clean inspection — open question, see `_resolution.py`).

> Note: per-file success tracking is currently approximated by
> `queue.taken ∪ jsonl.files`. Tightening this requires the agent pool
> to mark per-file outcomes in the queue, which is its own ticket.

---

## The four user-facing views, mapped to predicates

| view | rule | implementation |
|---|---|---|
| **Overview cards** (default landing) | Latest valid run per dim, resolved as-of the selected day. Default day = today. | `resolve_latest_per_dim(as_of=...)` |
| **Overview headline** | `mean(card.score for card in cards)` | computed in JS from cards |
| **Score-history chart bars** | One bar per day (current bucket); each bar's score = the day's latest successful run. | `bucket_runs_by_day(...)` (in `_buckets.py`) |
| **History table** | Successful runs only. | `is_successful_run(state, exit_reason)` |
| **Run navigator** | Explicit by run_id; no filter. | callers pass run_id directly |

Two invariants the package guarantees:

1. **Cards and headline can never disagree.** They draw from the same
   `resolve_latest_per_dim` output; the headline is `mean(cards)` so
   it's mathematically impossible for them to drift.
2. **History and overview agree on "successful".** Both views use the
   same `is_successful_run` predicate.

---

## Public API

See `__init__.py` for the canonical export list. Highlights:

- `is_successful_run(state, exit_reason)` — the success predicate.
- `is_trustable_run(state)` — for incremental salvage.
- `is_eligible_for_default_view(state)` — narrowest: cards/headline.
  Only `complete` qualifies; `in_progress` and `cancelled` are excluded
  so the overview waits for the umbrella run to terminate cleanly
  before counting any of its dims.
- `is_visible_in_history(reports_root, project, run_info)` — for the
  history table filter.
- `resolve_latest_per_dim(reports_root, project, *, as_of=None)` —
  the per-dim resolver, with optional date cutoff.
- `bucket_runs_by_day(runs)` — for the score-history chart.

Everything else is private (leading underscore on filenames). Reach
*through* `__init__.py`, never directly into `_states.py` etc.

---

## Migration status

This package is being introduced as a series of small PRs. Track
progress in the relevant PRs and in the call-sites file: every place
that used to compute its own filter now imports from here.

When the migration is done, `services/dim_resolution.py` (a thin
re-export shim from the previous iteration) gets deleted in a final
cleanup PR.
