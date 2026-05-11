# Plan 3 — API + Side-Tab UI

This adds three Flask routes and a React side tab on top of Plan 2's library.

## Routes

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/evaluations/<eval_id>/verify/<dimension>/<finding_id>` | Run the verifier for one finding; persist + return |
| GET  | `/api/evaluations/<eval_id>/verifications` | List all verifications for an eval |
| GET  | `/api/evaluations/<eval_id>/verifications/<verification_id>` | Fetch one with manifest + raw response |

Routes are registered only when `QUODEQ_VERIFIER_ENABLED=1`. Model defaults to
`gemma:4`; override with `QUODEQ_VERIFIER_MODEL`.

## Storage

Each evaluation gets a private SQLite database for verifications:

    ~/.quodeq/evaluations/<eval_id>/verifications.db

Heavy artifacts live alongside it:

    ~/.quodeq/evaluations/<eval_id>/verifier/<verification_id>/
      ├── manifest.json
      ├── prompt.system.txt
      ├── prompt.user.txt
      └── response.json

The DB stores small audit fields (verdict, confidence, evidence summary). The
audit-log directory stores everything else so future-you can replay a
verification without re-running Ollama.

## UI

The Verifier tab is a two-column layout:

- Left: list of findings from the current evaluation
- Right: detail panel — verdict, checklist, extracted facts, audit log

Selecting a finding shows a "▶ Verify" button. Clicking it blocks on the
verifier (~10–60s), then renders the full structured result.

The Verifier tab does not affect the main findings list. Plan 3 is the
trust-building phase; Phase 2 may surface verdicts in the main view.

## Phase 2 / 3 — not in Plan 3

- Auto-verify high-severity findings during evaluation runs
- SSE for verification progress
- Batch "Verify all" with parallelism
- Verdict-driven sort/collapse in the main findings list
- Frontier-model escalation for inconclusive results
