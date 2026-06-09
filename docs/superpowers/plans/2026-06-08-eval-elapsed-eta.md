# Live ELAPSED ticker + reading-speed/ETA subtext — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the running-evaluation ELAPSED card tick every second and add a `~1.2 files/s · ~5h left` subtext driven by a sliding-window throughput estimate.

**Architecture:** All estimate math lives as pure, framework-free helpers in `buildJobStatCells.js` (computeRate / formatRate / formatEta / buildEtaHint). `JobStatStrip.jsx` owns the React wiring: a 1-second tick that recomputes wall-clock elapsed, and a windowed sample buffer (one sample per progress poll) fed into the pure helpers. No backend changes.

**Tech Stack:** React (hooks), @tanstack/react-query (existing 2s progress poll), `node:test` for pure-helper unit tests, `vitest` + @testing-library/react for the component test.

Spec: `docs/superpowers/specs/2026-06-08-eval-elapsed-eta-design.md`

All commands run from the UI package root:
`cd /Users/victor/GitHub/quodeq/src/quodeq/ui`

---

## File Structure

- **Modify** `src/features/evaluation/components/buildJobStatCells.js` — add `RATE_WINDOW_MS`, `computeRate`, `formatRate`, `formatEta`, `buildEtaHint`; thread an `etaHint` input into the running branch's ELAPSED cell.
- **Modify** `src/features/evaluation/components/buildJobStatCells.test.js` — `node:test` units for the new helpers (existing tests untouched).
- **Modify** `src/features/evaluation/components/JobStatStrip.jsx` — 1s ticker, windowed sample buffer, wall-clock elapsed, wire `rate`/`etaHint`.
- **Modify** `src/features/evaluation/components/JobStatStrip.test.jsx` — `vitest` tests for the subtext + ticking (existing tests untouched).

---

## Task 1: `computeRate` sliding-window throughput

**Files:**
- Modify: `src/features/evaluation/components/buildJobStatCells.js`
- Test: `src/features/evaluation/components/buildJobStatCells.test.js`

- [ ] **Step 1: Write the failing test** — append to `buildJobStatCells.test.js`:

```js
import { computeRate, RATE_WINDOW_MS } from './buildJobStatCells.js';

test('computeRate: files/sec from oldest→newest over the window', () => {
  // 30 files over 30s = 1.0 files/s
  const s = [{ t: 1_000_000, taken: 10 }, { t: 1_030_000, taken: 40 }];
  assert.equal(computeRate(s), 1);
});

test('computeRate: null when fewer than 2 samples', () => {
  assert.equal(computeRate([]), null);
  assert.equal(computeRate([{ t: 1, taken: 5 }]), null);
  assert.equal(computeRate(null), null);
});

test('computeRate: null when window span is below the minimum (~15s)', () => {
  // 10s span -> not enough to be honest yet
  const s = [{ t: 1_000_000, taken: 10 }, { t: 1_010_000, taken: 30 }];
  assert.equal(computeRate(s), null);
});

test('computeRate: null when files have not advanced (stalled)', () => {
  const s = [{ t: 1_000_000, taken: 50 }, { t: 1_040_000, taken: 50 }];
  assert.equal(computeRate(s), null);
});

test('RATE_WINDOW_MS is exported for the buffer to window against', () => {
  assert.equal(typeof RATE_WINDOW_MS, 'number');
  assert.ok(RATE_WINDOW_MS > 0);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test src/features/evaluation/components/buildJobStatCells.test.js`
Expected: FAIL — `computeRate is not a function` / `RATE_WINDOW_MS` undefined.

- [ ] **Step 3: Write minimal implementation** — add near the top of `buildJobStatCells.js` (after the file header comment):

```js
// Throughput estimate tuning. The rate is measured over a sliding window so it
// reflects *current* speed (cache-hit bursts vs slow LLM misses, and the
// per-dimension speed shifts) rather than a startup-biased lifetime average.
export const RATE_WINDOW_MS = 60000;   // sliding window the buffer is trimmed to
const RATE_MIN_SPAN_MS = 15000;        // refuse to estimate from < this much data

/**
 * Files/sec from a buffer of {t, taken} samples (t = epoch ms, ascending).
 * Returns null — meaning "no honest estimate yet" — when there are fewer than
 * two samples, the window spans less than RATE_MIN_SPAN_MS, or files have not
 * advanced across the window (a stall).
 * @param {Array<{t:number, taken:number}>} samples
 * @returns {number|null}
 */
export function computeRate(samples) {
  if (!Array.isArray(samples) || samples.length < 2) return null;
  const oldest = samples[0];
  const newest = samples[samples.length - 1];
  const spanMs = newest.t - oldest.t;
  if (spanMs < RATE_MIN_SPAN_MS) return null;
  const dFiles = newest.taken - oldest.taken;
  if (dFiles <= 0) return null;
  return dFiles / (spanMs / 1000);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test src/features/evaluation/components/buildJobStatCells.test.js`
Expected: PASS (all tests in the file, old + new).

- [ ] **Step 5: Commit**

```bash
git add src/features/evaluation/components/buildJobStatCells.js src/features/evaluation/components/buildJobStatCells.test.js
git commit -m "feat(eval-strip): add computeRate sliding-window throughput helper"
```

---

## Task 2: `formatRate` + `formatEta` formatters

**Files:**
- Modify: `src/features/evaluation/components/buildJobStatCells.js`
- Test: `src/features/evaluation/components/buildJobStatCells.test.js`

- [ ] **Step 1: Write the failing test** — append to `buildJobStatCells.test.js`:

```js
import { formatRate, formatEta } from './buildJobStatCells.js';

test('formatRate: one decimal below 10/s, integer at/above 10/s', () => {
  assert.equal(formatRate(1.234), '~1.2 files/s');
  assert.equal(formatRate(9.96), '~10.0 files/s'); // toFixed rounds; still < 10 path
  assert.equal(formatRate(12.7), '~13 files/s');
});

test('formatRate: null for non-positive / non-finite / null', () => {
  assert.equal(formatRate(0), null);
  assert.equal(formatRate(-1), null);
  assert.equal(formatRate(Infinity), null);
  assert.equal(formatRate(null), null);
});

test('formatEta: "finishing" when essentially done', () => {
  assert.equal(formatEta(0, 1), 'finishing');     // nothing left
  assert.equal(formatEta(40, 1), 'finishing');    // 40s <= 45s
});

test('formatEta: minute buckets (nearest 1 under 10m, nearest 5 over)', () => {
  assert.equal(formatEta(120, 1), '~2 min left');   // 120s
  assert.equal(formatEta(1000, 1), '~15 min left'); // 1000s ≈ 16.7m -> nearest 5 = 15
  assert.equal(formatEta(50, 1), '~1 min left');    // 50s -> 1m (just over the 45s floor)
});

test('formatEta: hour buckets, minutes to nearest 5, carry at 60', () => {
  assert.equal(formatEta(18000, 1), '~5h left');        // 5h exactly
  assert.equal(formatEta(19800, 1), '~5h 30m left');    // 5h30m
  assert.equal(formatEta(7080, 1), '~2h left');         // 1h58m -> minutes round to 60 -> carry
});

test('formatEta: estimating when rate is unusable', () => {
  assert.equal(formatEta(100, 0), 'estimating…');
  assert.equal(formatEta(100, null), 'estimating…');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test src/features/evaluation/components/buildJobStatCells.test.js`
Expected: FAIL — `formatRate` / `formatEta` not a function.

- [ ] **Step 3: Write minimal implementation** — add to `buildJobStatCells.js` (below `computeRate`):

```js
/** "~1.2 files/s" (1 decimal below 10/s, integer above). null when unusable. */
export function formatRate(rate) {
  if (rate == null || !Number.isFinite(rate) || rate <= 0) return null;
  const shown = rate < 10 ? rate.toFixed(1) : String(Math.round(rate));
  return `~${shown} files/s`;
}

/**
 * Coarse, human-readable time remaining from files-left + files/sec rate.
 * "finishing" near the end; "~N min left"; "~Hh left" / "~Hh Mm left".
 * Returns "estimating…" if rate is unusable (caller normally gates first).
 */
export function formatEta(remainingFiles, rate) {
  if (!(rate > 0) || !Number.isFinite(rate)) return 'estimating…';
  if (remainingFiles <= 0) return 'finishing';
  const etaSec = remainingFiles / rate;
  if (etaSec <= 45) return 'finishing';
  if (etaSec < 3600) {
    const rawMin = etaSec / 60;
    let min = rawMin < 10 ? Math.max(1, Math.round(rawMin)) : Math.round(rawMin / 5) * 5;
    if (min >= 60) return '~1h left';
    return `~${min} min left`;
  }
  let hours = Math.floor(etaSec / 3600);
  let min = Math.round(((etaSec % 3600) / 60) / 5) * 5;
  if (min === 60) { hours += 1; min = 0; }
  return min === 0 ? `~${hours}h left` : `~${hours}h ${min}m left`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test src/features/evaluation/components/buildJobStatCells.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/features/evaluation/components/buildJobStatCells.js src/features/evaluation/components/buildJobStatCells.test.js
git commit -m "feat(eval-strip): add formatRate + formatEta human-readable formatters"
```

---

## Task 3: `buildEtaHint` combiner + wire into `buildJobStatCells`

**Files:**
- Modify: `src/features/evaluation/components/buildJobStatCells.js`
- Test: `src/features/evaluation/components/buildJobStatCells.test.js`

- [ ] **Step 1: Write the failing test** — append to `buildJobStatCells.test.js`:

```js
import { buildEtaHint } from './buildJobStatCells.js';

test('buildEtaHint: null when total is unknown (preparing…)', () => {
  assert.equal(buildEtaHint({ rate: 1, takenFiles: 0, totalFiles: 0 }), null);
});

test('buildEtaHint: "estimating…" when rate is unusable but total is known', () => {
  assert.equal(buildEtaHint({ rate: null, takenFiles: 5, totalFiles: 100 }), 'estimating…');
});

test('buildEtaHint: "~rate files/s · ~eta" when estimate is available', () => {
  // 90 files left at 1 file/s = 90s -> "~2 min left"
  assert.equal(
    buildEtaHint({ rate: 1, takenFiles: 10, totalFiles: 100 }),
    '~1.0 files/s · ~2 min left',
  );
});

test('buildJobStatCells: running ELAPSED cell carries the etaHint as its subtext', () => {
  const cells = buildJobStatCells('running', { ...baseInputs, etaHint: '~1.2 files/s · ~5h left' });
  assert.equal(cells[3].label, 'ELAPSED');
  assert.equal(cells[3].hint, '~1.2 files/s · ~5h left');
});

test('buildJobStatCells: done DURATION cell ignores etaHint', () => {
  const cells = buildJobStatCells('done', { ...baseInputs, takenFiles: 220, etaHint: 'should-not-appear' });
  assert.equal(cells[3].label, 'DURATION');
  assert.equal(cells[3].hint, 'total');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test src/features/evaluation/components/buildJobStatCells.test.js`
Expected: FAIL — `buildEtaHint` undefined; running ELAPSED `hint` is `null` not the etaHint.

- [ ] **Step 3: Write minimal implementation**

3a. Add to `buildJobStatCells.js` (below `formatEta`):

```js
/**
 * ELAPSED subtext for a running job: "~1.2 files/s · ~5h left".
 *  - null  when totalFiles is unknown (the PROGRESS card shows "preparing…").
 *  - "estimating…" when total is known but the rate isn't trustworthy yet.
 * @param {{rate:number|null, takenFiles:number, totalFiles:number}} args
 */
export function buildEtaHint({ rate, takenFiles, totalFiles }) {
  if (!(totalFiles > 0)) return null;
  const rateStr = formatRate(rate);
  if (rateStr == null) return 'estimating…';
  return `${rateStr} · ${formatEta(totalFiles - takenFiles, rate)}`;
}
```

3b. In `buildJobStatCells.js`, change the running branch's ELAPSED cell to pass the hint. Find:

```js
    foundCell(inputs.liveCount),
    elapsedCell(inputs.elapsedS),
  ];
```

Replace with:

```js
    foundCell(inputs.liveCount),
    elapsedCell(inputs.elapsedS, 'ELAPSED', inputs.etaHint ?? null),
  ];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test src/features/evaluation/components/buildJobStatCells.test.js`
Expected: PASS (old + new).

- [ ] **Step 5: Commit**

```bash
git add src/features/evaluation/components/buildJobStatCells.js src/features/evaluation/components/buildJobStatCells.test.js
git commit -m "feat(eval-strip): combine rate+eta into ELAPSED subtext hint"
```

---

## Task 4: Wire `JobStatStrip` — 1s ticker, sample buffer, wall-clock elapsed

**Files:**
- Modify: `src/features/evaluation/components/JobStatStrip.jsx`
- Test: `src/features/evaluation/components/JobStatStrip.test.jsx`

- [ ] **Step 1: Write the failing tests** — append inside the `describe('JobStatStrip', …)` block in `JobStatStrip.test.jsx`:

```js
  it('shows "estimating…" subtext for a fresh running job (one sample)', async () => {
    getEvaluationProgress.mockResolvedValue({
      dimensions: [{ state: 'running', files: { taken: 10, total: 1000 } }],
    });
    const job = { jobId: 'job-3', status: 'running', startedAt: new Date(Date.now() - 5000).toISOString() };
    renderWithClient(<JobStatStrip job={job} liveViolations={{}} />);
    expect(await screen.findByText('estimating…')).toBeInTheDocument();
  });

  it('ELAPSED reflects wall-clock from startedAt (not backend elapsed)', async () => {
    const now = new Date('2026-06-08T10:00:00Z').getTime();
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(now);
    getEvaluationProgress.mockResolvedValue({
      dimensions: [{ state: 'running', files: { taken: 10, total: 1000 } }],
      totalElapsedS: 9999, // would show 166:39 if backend value were used
    });
    const job = { jobId: 'job-4', status: 'running', startedAt: new Date(now - 5000).toISOString() };
    renderWithClient(<JobStatStrip job={job} liveViolations={{}} />);
    expect(await screen.findByText('0:05')).toBeInTheDocument();
    nowSpy.mockRestore();
  });

  it('ELAPSED ticks forward each second', async () => {
    vi.useFakeTimers();
    try {
      const t0 = new Date('2026-06-08T10:00:00Z').getTime();
      vi.setSystemTime(t0);
      getEvaluationProgress.mockResolvedValue({
        dimensions: [{ state: 'running', files: { taken: 10, total: 1000 } }],
      });
      const job = { jobId: 'job-5', status: 'running', startedAt: new Date(t0 - 5000).toISOString() };
      renderWithClient(<JobStatStrip job={job} liveViolations={{}} />);
      await vi.advanceTimersByTimeAsync(0);     // flush the initial fetch
      expect(screen.getByText('0:05')).toBeInTheDocument();
      await vi.advanceTimersByTimeAsync(2000);  // two 1s ticks
      expect(screen.getByText('0:07')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run src/features/evaluation/components/JobStatStrip.test.jsx`
Expected: FAIL — no `estimating…` text; ELAPSED shows backend-derived value, not `0:05`/`0:07`.

- [ ] **Step 3: Write the implementation** — replace the entire contents of `JobStatStrip.jsx` with:

```jsx
import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getEvaluationProgress } from '../../../api/index.js';
import { evaluationKeys } from '../../../api/queryKeys.js';
import { StatStrip, Stat } from '../../../components/terminal/index.js';
import { computeOverallProgress } from './scanProgressTotals.js';
import { buildJobStatCells, computeRate, buildEtaHint, RATE_WINDOW_MS } from './buildJobStatCells.js';

const POLL_INTERVAL_MS = 2000;
const TICK_INTERVAL_MS = 1000;
const TERMINAL_STATES = new Set(['done', 'completed', 'failed', 'cancelled', 'lost']);

function sumLiveViolations(liveViolations) {
  if (!liveViolations) return 0;
  return Object.values(liveViolations).reduce((n, vs) => n + (vs?.length || 0), 0);
}

// Live elapsed from wall-clock so the cell ticks every second between the 2s
// progress polls. Falls back to the backend-reported elapsed only when the job
// carries no usable startedAt.
function deriveElapsedS(startedAt, endedAt, isTerminal, fallbackElapsed) {
  if (startedAt) {
    const start = Date.parse(startedAt);
    if (!Number.isNaN(start)) {
      const end = isTerminal && endedAt ? Date.parse(endedAt) : Date.now();
      if (!Number.isNaN(end)) return Math.max(0, (end - start) / 1000);
    }
  }
  if (fallbackElapsed != null && Number.isFinite(fallbackElapsed)) return fallbackElapsed;
  return null;
}

export default function JobStatStrip({ job, liveViolations }) {
  const jobId = job?.jobId;
  const isTerminal = TERMINAL_STATES.has(job?.status);

  const { data: progress, dataUpdatedAt } = useQuery({
    queryKey: jobId ? [...evaluationKeys.evaluation(jobId), 'progress'] : ['evaluation', '_none_', 'progress'],
    queryFn: () => getEvaluationProgress(jobId),
    enabled: !!jobId,
    refetchInterval: isTerminal ? false : POLL_INTERVAL_MS,
    staleTime: 0,
    retry: false,
  });

  // Per-second re-render so wall-clock elapsed advances between the 2s polls.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (isTerminal || !jobId) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), TICK_INTERVAL_MS);
    return () => clearInterval(id);
  }, [isTerminal, jobId]);

  // Throughput samples: one per completed poll (keyed on dataUpdatedAt, which
  // advances every poll even when the data is identical — so a stall registers
  // as flat samples). Trimmed to RATE_WINDOW_MS. Kept in a ref so pushes don't
  // trigger renders; the 1s tick picks the new sample up within a second.
  const samplesRef = useRef([]);
  useEffect(() => { samplesRef.current = []; }, [jobId]);
  useEffect(() => {
    if (!progress || isTerminal) return;
    const { takenFiles, totalFiles } = computeOverallProgress(progress);
    if (!(totalFiles > 0)) return;
    const now = Date.now();
    const buf = samplesRef.current;
    buf.push({ t: now, taken: takenFiles });
    while (buf.length > 1 && now - buf[0].t > RATE_WINDOW_MS) buf.shift();
  }, [dataUpdatedAt, isTerminal, progress]);

  const cells = useMemo(() => {
    if (!jobId) return [];
    const { takenFiles, totalFiles, overallPct } = computeOverallProgress(progress);
    const elapsedS = deriveElapsedS(job?.startedAt, job?.endedAt, isTerminal, progress?.totalElapsedS);
    const liveCount = sumLiveViolations(liveViolations);
    const rate = isTerminal ? null : computeRate(samplesRef.current);
    const etaHint = isTerminal ? null : buildEtaHint({ rate, takenFiles, totalFiles });
    return buildJobStatCells(job.status, { overallPct, takenFiles, totalFiles, elapsedS, liveCount, etaHint });
    // `tick` drives the per-second recompute; samplesRef is read (not a dep).
  }, [jobId, job?.status, job?.startedAt, job?.endedAt, isTerminal, progress, liveViolations, tick]);

  if (!jobId) return null;

  return (
    <div className="eval-job-stat-strip">
      <StatStrip cards>
        {cells.map((c) => (
          <Stat key={c.label} label={c.label} value={c.value} hint={c.hint} tone={c.tone} />
        ))}
      </StatStrip>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run src/features/evaluation/components/JobStatStrip.test.jsx`
Expected: PASS — including the 4 pre-existing tests (they pass no `startedAt`, so elapsed falls back to `totalElapsedS` and still reads `2:14` / `4:32`).

Note: if the fake-timer test (`ticks forward each second`) is flaky against react-query's internal timers, keep the `estimating…` and Date.now-spy tests (they cover the new behavior) and assert the tick via the same `Date.now` spy incremented between `vi.advanceTimersByTime` calls. Do not weaken the other two tests.

- [ ] **Step 5: Run the full UI suite to confirm nothing regressed**

Run: `npm run test && npm run test:ui`
Expected: PASS for both runners.

- [ ] **Step 6: Commit**

```bash
git add src/features/evaluation/components/JobStatStrip.jsx src/features/evaluation/components/JobStatStrip.test.jsx
git commit -m "feat(eval-strip): tick ELAPSED every second + show files/s and ETA"
```

---

## Definition of Done

- Pure helpers `computeRate`/`formatRate`/`formatEta`/`buildEtaHint` exist and are unit-tested (`node --test`).
- Running ELAPSED card ticks every second from wall-clock; subtext shows `~<rate> files/s · <eta>`, `estimating…` before enough data, and nothing while `preparing…`.
- Terminal states are unchanged (DURATION/total, no ETA, no ticker).
- `npm run test` and `npm run test:ui` both pass.
- Manual check: `quodeq dashboard`, start a scan, confirm ELAPSED ticks 1s and the subtext appears and updates.
