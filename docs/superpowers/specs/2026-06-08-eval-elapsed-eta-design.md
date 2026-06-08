# Live ELAPSED ticker + reading-speed/ETA subtext

Date: 2026-06-08
Status: Approved design, pending implementation plan
Area: Web dashboard, evaluation stat strip (`src/quodeq/ui/src/features/evaluation/`)

## Problem

On the running-evaluation panel (`JobStatStrip`), the ELAPSED card only updates
when the progress poll fires (`POLL_INTERVAL_MS = 2000`), so the clock visibly
jumps every ~2 seconds. There is also no estimate of how much longer the run
will take. For a 6-dimension run over thousands of files (which can take hours),
the operator has no sense of remaining time or current throughput.

## Goals

1. ELAPSED advances smoothly, **once per second**.
2. A subtext under ELAPSED shows the **current reading speed and a rough,
   human-readable time remaining**, e.g. `~1.2 files/s · ~5h left`.
3. The estimate is **honest**: it shows the *current* throughput (not a
   lifetime average), and it refuses to print a number when it does not yet
   have enough data (shows `estimating…`).

## Non-goals

- No backend changes. All inputs (`takenFiles`, `totalFiles`, `startedAt`) are
  already available client-side.
- No precision guarantee. The estimate is explicitly rough and coarse-bucketed.
- No ETA on terminal states (done/failed/cancelled/lost keep DURATION/total).

## Design

### Part 1 — second-by-second ELAPSED

`JobStatStrip` adds a 1-second `setInterval` tick (a `useState` counter) that is
active only while the job is non-terminal. Each tick re-renders the strip.
`elapsedS` for the display is derived from wall-clock
(`(Date.now() - Date.parse(job.startedAt)) / 1000`) so it advances between the
2s polls. On a terminal state the interval is cleared and elapsed freezes to
`(endedAt - startedAt)`. This replaces reliance on `progress.totalElapsedS` for
the *live* display; the backend value is no longer needed for ticking (the
wall-clock delta is accurate to within the poll skew and updates every second).

### Part 2 — `~1.2 files/s · ~5h left` subtext

**Rate: sliding window.** `JobStatStrip` keeps a `useRef` buffer of samples
`{ t, taken }`. A sample is pushed **once per completed poll** — the push effect
is keyed on the query's `dataUpdatedAt` (which advances every poll even when the
data is identical), NOT on the 1s tick and NOT on `takenFiles` changing. Pushing
on every poll regardless of change is deliberate: a stall then shows up as a run
of flat samples (`Δfiles == 0` across the window), which the guard below detects.
Samples older than `WINDOW_MS` (~60s) are dropped. The rate is:

```
rate = (newest.taken - oldest.taken) / ((newest.t - oldest.t) / 1000)   // files/sec
```

This reflects current throughput and sheds the slow agent/model warmup at t=0.

**ETA.** `etaSec = (totalFiles - takenFiles) / rate`.

**Formatting (pure helpers in `buildJobStatCells.js`):**

- `formatRate(rate)` → `~1.2 files/s` (1 decimal below 10/s, integer above).
- `formatEta(remainingFiles, rate)` → coarse human bucket:
  - `remainingFiles <= 0` or `etaSec <= 45` → `finishing`
  - `etaSec < 3600` → `~M min left`, where M = round(etaSec/60), rounded to the
    nearest 1 minute below 10, nearest 5 minutes from 10–59.
  - `etaSec >= 3600` → `~Hh left` or `~Hh Mm left`, with minutes rounded to the
    nearest 5 (carry to the hour at 60; drop the minutes term when 0).
- Combined subtext: `${formatRate(rate)} · ${formatEta(...)}`.

**Accountability guard — when to show `estimating…` instead of a number.**
`computeRate(samples)` returns `null` (→ subtext = `estimating…`) when any of:

- fewer than 2 samples, or
- window span `< MIN_WINDOW_S` (~15s) — too little data to be honest, or
- `Δfiles <= 0` across the window — files have stalled, so a 0/near-0 rate
  would yield a meaningless or infinite ETA.

When `totalFiles` is unknown (0, the `preparing…` window), the subtext is
omitted entirely (`hint = null`), consistent with the PROGRESS card showing
`preparing…`.

### Code placement and boundaries

- **`buildJobStatCells.js`** (pure, no React/DOM — existing contract): new
  helpers `computeRate(samples, nowMs)`, `formatRate(rate)`,
  `formatEta(remainingFiles, rate)`. The running branch's `elapsedCell` receives
  the computed subtext as its `hint`.
- **`JobStatStrip.jsx`**: owns the 1s ticker (`useEffect` + `setInterval`), the
  sample-buffer `useRef`, and the per-poll push effect. It derives wall-clock
  `elapsedS` and calls the pure helpers. No business logic lives in the
  component beyond wiring.

## Edge cases

- Job not started / no `startedAt` → elapsed `—`, no subtext.
- Terminal state → DURATION/total, no ticker, no ETA.
- `takenFiles` stalls mid-run → `estimating…` (guard), recovers when it advances.
- `totalFiles` revised upward as dims reveal queues → ETA recomputes naturally;
  the sliding window keeps it current.
- Very fast finish → `finishing`.

## Testing

- Unit (`buildJobStatCells.test.js` style):
  - `computeRate`: normal window, `<2` samples → null, span `< MIN_WINDOW_S` →
    null, stalled (`Δfiles <= 0`) → null, old-sample eviction.
  - `formatRate`: sub-10 decimal vs integer.
  - `formatEta`: `finishing` (≤45s and remaining≤0), minute buckets (rounding
    below 10 vs nearest-5), hour buckets (with/without minutes, carry at 60).
- Component (`JobStatStrip.test.jsx` style): elapsed advances on a faked 1s
  interval; subtext renders `~rate files/s · …`; `estimating…` before enough
  data; no subtext on terminal/`preparing…`.

## Out of scope / future

- Per-dimension ETA breakdown.
- Persisting throughput history across reconnects (the in-memory window resets
  on remount; acceptable — it refills within `WINDOW_MS`).
