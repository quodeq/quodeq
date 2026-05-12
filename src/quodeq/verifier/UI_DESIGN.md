# Verifier UI Design

**Status:** Spec, awaiting implementation.
**Branch:** `experimental/finding-verifier`
**Date:** 2026-05-12
**Companion to:** [`RETROSPECTIVE.md`](RETROSPECTIVE.md) — read first for the analysis that informed these decisions.

## Context

The verifier subsystem (resolver → manifest → multi-block evidence → LLM → deterministic verdict) shipped on this branch as a working but loosely-surfaced feature: a side-tab UI gated behind `QUODEQ_VERIFIER_ENABLED=1`, with verdicts persisted but not promoted into the main flow.

The retrospective measured the architecture, weighed an upstream-pivot (move evidence pipeline into the evaluator), and recommended against it for the current product moment. This spec is the alternative path the retrospective implicitly endorsed: **keep the verifier as a user-triggered external feature, but make it first-class** — inline on every violation row, configured via settings, accessible without env vars.

### Architectural anchor

**The verifier stays an external, user-triggered process.** Not auto-run during evaluation. Not pulled into the evaluator's prompt pipeline. Every verification is an explicit user click. This is a deliberate decision; the reasoning lives in `RETROSPECTIVE.md` (sections "What we (re-)discovered about the architecture" and "Recommendation: move the evidence pipeline upstream").

The summary of why we did *not* take the upstream pivot:

- Adding manifest context upstream doesn't lift the Gemma reasoning ceiling; it just moves the bad reasoning earlier.
- Token bloat on every evaluator call for the 57% of findings with no useful cross-file evidence.
- A pre-LLM rules pre-filter on the manifest is the right *eventual* win, but it's a separate workstream from making the user-facing feature usable today.

The work in this spec stands on its own and does not preclude that future pivot.

## 1. UI surface

Every violation row in `FileDetailPage` and `PrincipleDetailPage` (both render `ViolationCard`) gets a right-aligned action cluster:

```
[ verdict badge ] · Fix plan · Verify · 🗑
```

### 1.1 Verdict badge (`VerificationBadge`)

- 18×18 tinted disc — `border-radius: 50%`, `~15% alpha` background, full-saturation char inside.
- Char per verdict: `✓` false_positive · `!` confirmed · `?` inconclusive · `i` not_applicable (legacy).
- Colors come from semantic theme tokens — `--color-success`, `--color-danger`, `--color-text-muted` — so the badge auto-adapts to light/dark and the Flynn dark theme.
- When no verdict exists, render an empty 18×18 placeholder dot so the column stays aligned across rows.
- When the last attempt errored, render a `⚠` marker in place of the verdict (color: `--color-warning`).

### 1.2 Hover tooltip (verdict badge)

Custom CSS tooltip (not native `title`) so we can format two lines and color the verdict.

```
False positive · 82%       ← verdict color, bold
Ollama · gemma4:e4b        ← muted, smaller
```

For `error` state, the tooltip shows the failure reason, e.g. `LLM unreachable — is Ollama running?`.

### 1.3 Verify button

- Text button matching the existing `Fix plan` outlined style — same height, border, hover treatment.
- Label depends on state:
  - `idle` (no prior verdict) → "Verify"
  - `verdict` exists → "↻ Re-verify"
  - `error` → "↻ Retry"
  - `verifying` → "Verifying…" + small inline spinner, disabled
  - `queued` → "Queued…", disabled
- Disabled treatment: same border, opacity 0.6, no hover effect.

### 1.4 Dismiss (🗑)

Unchanged. Stays icon-only at modest weight, same visual language as today.

## 2. Settings

A new block, "**Verification**", in the settings panel. Mirrors the layout/pattern of the existing analysis block (pill-button rows + help hints, no real toggle switches).

### 2.1 Fields (state keys in parens)

1. **Enable verification** (`verifier-enabled`, default `false`)
   - Pill `On / Off`.
   - When `Off`: Verify button is hidden on all violation rows; backend rejects verify calls with HTTP 403.

2. **Use analysis model** (`verifier-use-analysis-model`, default `true`)
   - Pill `Yes / Custom`. Only visible when `verifier-enabled = true`.
   - When `Yes`: inline note "Currently inherits: `<provider> · <model>`", no extra pickers.
   - When `Custom`: reveals fields 3 and 4.

3. **Provider** (`verifier-provider`) — `<select>` of installed providers, same list as analysis (Ollama, llama.cpp, Claude CLI, Cloud).

4. **Model** (`verifier-model`) — `<select>` of models available for the chosen provider, powered by the existing model-discovery used by the analysis side.

### 2.2 Naming and clash handling

The existing settings state has a `verify` key (in `ProviderSettings.jsx:105`) that controls **re-evaluation cache invalidation** ("recheck cached findings on re-run") — a different feature with a different lifecycle from on-demand verification.

- The existing setting's **label** is renamed to "**Recheck findings on re-run**" so users don't confuse it with the new Verification block. State key stays `verify` (no migration needed).
- All new keys use the `verifier-*` prefix to avoid any future overlap.

### 2.3 Backend wiring

The verifier service reads these settings on each verify request (not at boot, so live changes take effect without a restart). Resolution order per request:

1. `verifier-enabled = false` → HTTP 403 "verification disabled". (Defensive; the frontend should already hide the button.)
2. `verifier-use-analysis-model = true` → use the same provider/model the analysis side is configured for.
3. Otherwise → use `verifier-provider` + `verifier-model`.

The current `QUODEQ_VERIFIER_MODEL` env var is dropped; no fallback period.

## 3. Behavior & state machine

### 3.1 Per-row Verify button state

| State | Trigger | Visual |
|---|---|---|
| `idle` | initial, no verdict cached | "Verify" label, badge slot empty (·) |
| `queued` | clicked while local provider is busy on another row | "Queued…" label, disabled, badge slot empty (·) |
| `verifying` | this row's call is in flight | "Verifying…" + spinner, disabled, badge slot empty (·) |
| `verdict` | call returned successfully | "↻ Re-verify" label, badge slot shows verdict disc |
| `error` | call failed (503/504/502) | "↻ Retry" label, badge slot shows ⚠ marker (with hover error reason) |

### 3.2 Concurrency

- **Local provider** (Ollama, llama.cpp): single in-flight verification globally. Other clicks → FIFO queue. Per-row state goes `idle → queued → verifying → verdict|error`.
- **Cloud provider** (Claude API, OpenRouter, etc.): no queue. Each click goes straight to `verifying`. State goes `idle → verifying → verdict|error`.
- Provider classification (local vs cloud) comes from the existing `classifyProvider` in `providerUtils.js`.
- Concurrency is enforced **frontend-only**. The backend doesn't enforce; if two clients somehow race, both calls run. The local model's serial nature is the natural throttle. Backend queueing isn't worth the complexity for a single-user-per-instance tool.

### 3.3 Error handling

- `LLMUnreachableError` (HTTP 503) — first occurrence in the session toasts "Verifier unreachable — is Ollama running?" plus persistent ⚠ in the badge slot. Repeat failures within ~60s don't re-toast (badge marker only). Hover tooltip on ⚠: "LLM unreachable".
- `VerifierTimeoutError` (HTTP 504) — silent ⚠ in badge slot, no toast. Hover tooltip on ⚠: "Verification timed out".
- `MalformedResponseError` (HTTP 502) — silent ⚠ in badge slot, no toast. Hover tooltip on ⚠: "Verifier returned a malformed response".
- Toast policy is per session-level error type, not per row.
- **Error state is frontend-ephemeral.** A failed verify call does not write anything to `verifications.db`. The ⚠ marker only persists for the current page mount; on refresh, the badge falls back to whatever verdict is persisted (or empty if none). The user can retry to either confirm the failure is reproducible or recover a fresh verdict.

### 3.4 Re-verify

Overwrites prior verdict in storage. No history kept; the badge always reflects the latest call. (Model attribution in the tooltip makes "I just re-verified with Claude" obvious without persisting a history.)

### 3.5 View persistence

- Verdicts come from the existing per-eval `verifications.db` SQLite store.
- On page mount, the frontend fetches all verifications for the current eval in **one** HTTP call (`GET /api/evaluations/<eval_id>/verifications`) and hydrates the badge column from that map.
- No per-row fetches.

## 4. Backend changes

### 4.1 Verification record schema (`verifier/models.py`)

- Add `provider: str = ""` field alongside the existing `model: str`.
- Populated at write-time from the active verifier provider configuration.
- Powers the tooltip's `"Ollama · gemma4:e4b"` line.

### 4.2 Routes

| Route | Change |
|---|---|
| `POST /api/evaluations/<eval_id>/verify/<dimension>/<finding_id>` | Always registered (no env-var gate). Per-request settings check controls behavior. Returns 403 when `verifier-enabled = false`. |
| `GET /api/evaluations/<eval_id>/verifications` | Unchanged. Used on detail-page mount to hydrate badges. |
| `GET /api/evaluations/<eval_id>/verifications/<verification_id>` | Unchanged. Kept for forensic inspection; no UI surface in this design. |

### 4.3 Removals

- `QUODEQ_VERIFIER_ENABLED` env var and its registration gate in `api/app.py:198`.
- `QUODEQ_VERIFIER_MODEL` env var and its fallback path in the service layer.
- `tabs/Verifier.jsx` side-tab component and its route entry in `App.jsx`.

### 4.4 What stays

- `useVerifications` hook — repurposed to power the inline badges.
- `VerificationBadge` component — restyled per Section 1.1.
- The entire resolver / manifest / multi-block evidence pipeline — unchanged.
- All Python service-layer code (`verifier/service.py`, `verifier/verifier.py`, prompt, schema, verdict).

## 5. Cleanup, scope, and rollout

### 5.1 In-scope surfaces

- `FileDetailPage` violation rows
- `PrincipleDetailPage` violation rows
- New "Verification" settings block in the settings panel
- Settings rename of the existing "Verify findings" → "Recheck findings on re-run" (label only)

### 5.2 Out of scope (future, additive)

- Auto-verify on evaluation completion
- Batch / "verify all in this view"
- Verdict history (currently overwrite-only)
- Sorting / filtering the findings list by verdict
- A dedicated "show full audit log" UI on top of the existing detail endpoint

### 5.3 Backwards compatibility

- `Verdict.NOT_APPLICABLE` enum is retained so persisted v7.2 records still load and render. The v8/v9 path never produces it.
- Existing `verifications.db` files keep loading. Rows missing the new `provider` field render the tooltip with just the model name.

### 5.4 Rollout

- Single PR.
- No migration script. The new settings keys are additive; backend changes are harmless to existing installations.
- After upgrade, the Verification block defaults to **Off**. Users explicitly opt in — no surprise LLM calls on first launch.
- **Heads-up for existing users:** anyone who had `QUODEQ_VERIFIER_ENABLED=1` set previously will lose the feature until they flip the new Verification setting to On. Cover in the release notes; no automatic carry-over (the env var can't be reliably detected post-removal).

## 6. Open questions / things to revisit

- **Provider field for legacy records**: When a verification record has no `provider` field, the tooltip shows just the model name. If post-launch we want to backfill, a one-time script would need to infer provider from model-name heuristics (e.g. `gemma*` → Ollama). Not worth doing now; the gap closes naturally as users re-verify.
- **Cloud concurrency limits**: This spec says cloud verifications are unbounded. In practice, providers have rate limits. If we see issues, add a per-provider concurrency cap (e.g. 3 for Anthropic). Out of scope for v1.
- **Auto-discovery of installed providers in the verifier dropdown**: We assume `verifier-provider` shows the same list as analysis. If a user has Claude installed but only configured for analysis, do they need to repeat the API-key setup for the verifier? No — provider config is global. The verifier just consumes whatever the analysis provider tabs have configured.
