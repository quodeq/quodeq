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

A run's lifecycle state is `quodeq.core.run.state.RunState` (sourced from
`status.json` and the dashboard's external-process detection):

| state | meaning |
|---|---|
| `PENDING` | Not yet started. |
| `RUNNING` | Currently running. Dims that finish scoring mid-run produce trustworthy eval files immediately. |
| `FINALIZING` | Wrapping up after the last dimension finished. |
| `DONE` | Run reached a natural end — every configured dim scored, lifecycle transitioned to DONE. |
| `CANCELLED` | The run was stopped before natural completion. |
| `FAILED` | System error before or during scoring. Eval files written, if any, are not to be trusted. |

### Per-file granularity

Even within a run, individual files may have errored —
typical case: token exhaustion, agent retried twice, gave up. Those
files were *dispatched* (in `queue.taken`) but *no findings landed*
(absent from JSONL). Counting them as analyzed lets the next run
incorrectly skip them. The corrected rule: a file is "analyzed" only
if both the queue dispatched it AND it produced any evidence (or a
signal of clean inspection — still an open question).

> Note: per-file success tracking is currently approximated by
> `queue.taken ∪ jsonl.files`. Tightening this requires the agent pool
> to mark per-file outcomes in the queue, which is its own ticket.

---

## The two user-facing views this package still drives

| view | rule | implementation |
|---|---|---|
| **Overview cards / headline** (default landing) | Only a `DONE` run may be the headline; falls back to `CANCELLED` runs when no `DONE` run exists. | `select_default_view_runs` (`is_eligible_for_default_view`) |
| **Score-history / trend** | `DONE` and `RUNNING` runs; `CANCELLED` and `FAILED` are dropped — their partial scores are misleading as history points. | `select_trend_runs` (`TREND_STATES`) |

Both consult a single function so two call sites can never drift apart
(a class of bug hit repeatedly before centralisation): `accumulated._compute_result`
and `_fs_metadata._read_accumulated_summary` both call
`select_default_view_runs`; `_dashboard_history._compute_dashboard_payload`
and `scoring.get_project_scores` both call `select_trend_runs`.

---

## Public API

See `__init__.py` for the canonical export list. Highlights:

- `is_eligible_for_default_view(status: RunState)` — the strictest rule:
  only `DONE` qualifies; `RUNNING` and `CANCELLED` are both excluded so
  the overview waits for the umbrella run to terminate before counting
  any of its dims.
- `select_default_view_runs(run_infos)` — `DONE` runs when any exist,
  else the `CANCELLED` fallback.
- `select_trend_runs(run_infos)` / `TREND_STATES` — the trend/history-chart
  run set.

Everything else is private (leading underscore on filenames). Reach
*through* `__init__.py`, never directly into `_states.py` etc.

---

## Migration status

Done. `services/dim_resolution.py` (the re-export shim from the
previous iteration) has been deleted; every call site imports from
this package directly.

2026-09-22 (run-list-vocabulary-into-RunState migration): the
`RUN_STATE_*` string constants, `SUCCESSFUL_CANCEL_REASONS`,
`is_successful_run`, `is_trustable_run`, `resolve_latest_per_dim`,
`is_visible_in_history`, `is_eligible_for_chart_bar`,
`bucket_runs_by_day` and `pick_representative_run` were removed: a
`grep -rn <name> src` inventory showed none had a production caller
(the eval-file-provenance resolver and the score-history bucketing were
never wired into a live view). The `_resolution.py` / `_buckets.py`
stubs and the `DimResolution` / `BucketView` / `RunSummary` models they
were meant to produce followed (2026-09-23): nothing produced them.
