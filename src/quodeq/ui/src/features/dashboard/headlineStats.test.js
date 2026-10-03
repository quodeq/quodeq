import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildHeadline, chipDeltas, dimensionHeadlineInput, dimensionOpenTypes, filterSinceBaseline, periodChipDeltas, runCounts, sinceBaselineFor, sumSinceBaseline, SCOPE_ALL, SCOPE_CHANGED, SCOPE_MIXED } from './headlineStats.js';

const dim = (over = {}) => ({
  dimension: 'maintainability',
  totals: { violationCount: 10, complianceCount: 20, severity: { critical: 1, major: 2, minor: 7 } },
  violations: [{ req: 'M-A-1' }, { req: 'M-A-1' }, { req: 'M-B-2' }, {}],
  filesRead: 40, sourceFileCount: 50,
  ...over,
});

test('dimensionOpenTypes prefers the backend count, else distinct req', () => {
  assert.equal(dimensionOpenTypes(dim({ openTypes: 5 })), 5);
  assert.equal(dimensionOpenTypes(dim()), 2);
  assert.equal(dimensionOpenTypes({}), 0);
});

test('buildHeadline sums majors, open types, density and coverage over dimensions', () => {
  const h = buildHeadline([dim(), dim({ dimension: 'security', filesRead: 10, sourceFileCount: 50, totals: { violationCount: 2, complianceCount: 0, severity: { critical: 0, major: 0, minor: 2 } }, violations: [{ req: 'S-1' }] })]);
  assert.equal(h.majors, 3);
  assert.equal(h.critical, 1);
  assert.equal(h.openTypes, 3);
  assert.equal(h.violations, 12);
  assert.equal(h.filesRead, 50);
  assert.equal(h.sourceFileCount, 100);
  assert.equal(h.density, 24);        // 12 violations over 50 files read, per 100
  assert.equal(h.coveragePct, 50);
});

test('density is null when nothing was read', () => {
  const h = buildHeadline([dim({ filesRead: 0, sourceFileCount: 0 }), dim({ filesRead: undefined, sourceFileCount: undefined })]);
  assert.equal(h.density, null);
  assert.equal(h.coveragePct, null);
});

const entry = (over = {}) => ({
  againstRunId: 'r0', againstCommitSha: 'abc',
  sinceBaseline: { scope: SCOPE_CHANGED, changedFiles: 3, majorsDelta: -1, counts: { new: 2, resolved: 5 }, types: { closed: ['M-A-1'], opened: [] } },
  all: { majorsDelta: -2, counts: { new: 20, resolved: 50 }, types: { closed: ['M-A-1', 'M-C-3'], opened: ['M-D-4'] } },
  ...over,
});

test('sumSinceBaseline returns null on an empty payload', () => {
  assert.equal(sumSinceBaseline({}), null);
  assert.equal(sumSinceBaseline(undefined), null);
});

test('a first run has no baseline: entries without againstRunId are not a baseline', () => {
  const first = entry({ againstRunId: null, againstCommitSha: null, sinceBaseline: { scope: SCOPE_ALL, changedFiles: null, majorsDelta: 12, counts: { new: 300, resolved: 0 }, types: { closed: [], opened: ['M-A-1'] } }, all: { majorsDelta: 12, counts: { new: 300, resolved: 0 }, types: { closed: [], opened: ['M-A-1'] } } });
  assert.equal(sumSinceBaseline({ maintainability: first }), null);
});

test('a dimension new to the project is left out of the fold, not counted as a regression', () => {
  const fresh = entry({ againstRunId: null, sinceBaseline: { ...entry().sinceBaseline, majorsDelta: 9, types: { closed: [], opened: ['S-1'] } } });
  const s = sumSinceBaseline({ maintainability: entry(), security: fresh });
  assert.equal(s.scope, SCOPE_CHANGED);
  assert.equal(s.majorsDelta, -1);
  assert.deepEqual(s.typesOpened, []);
});

test('under one changed-files baseline every number comes from the scoped block', () => {
  const s = sumSinceBaseline({ maintainability: entry(), security: entry({ sinceBaseline: { ...entry().sinceBaseline, majorsDelta: 0, counts: { new: 1, resolved: 0 }, types: { closed: [], opened: ['S-9'] } } }) });
  assert.equal(s.majorsDelta, -1);
  assert.deepEqual(s.typesClosed, ['M-A-1']);
  assert.deepEqual(s.typesOpened, ['S-9']);
  assert.equal(s.newCount, 3);
  assert.equal(s.resolvedCount, 5);
  assert.equal(s.scope, SCOPE_CHANGED);
  assert.equal(s.changedFiles, 3);
  assert.deepEqual(s.againstRunIds, ['r0']);
});

test('an unchanged tree with re-sampled totals still folds to zero', () => {
  const quiet = entry({ sinceBaseline: { scope: SCOPE_CHANGED, changedFiles: 0, majorsDelta: 0, counts: { new: 0, resolved: 0 }, types: { closed: [], opened: [] } }, all: { majorsDelta: 3, counts: { new: 40, resolved: 12 }, types: { closed: [], opened: ['M-X-1'] } } });
  const s = sumSinceBaseline({ a: quiet });
  assert.deepEqual([s.majorsDelta, s.newCount, s.resolvedCount, s.typesOpened, s.changedFiles], [0, 0, 0, [], 0]);
});

test('any dimension scoped to all files makes the summary all-files, from the all block', () => {
  const s = sumSinceBaseline({ a: entry(), b: entry({ sinceBaseline: { ...entry().sinceBaseline, scope: SCOPE_ALL, changedFiles: null } }) });
  assert.equal(s.scope, SCOPE_ALL);
  assert.equal(s.changedFiles, null);
  assert.equal(s.majorsDelta, -4);
  assert.equal(s.newCount, 40);
  assert.deepEqual(s.typesClosed, ['M-A-1', 'M-C-3']);
});

test('an all block without counts falls back to the scoped counts', () => {
  const s = sumSinceBaseline({ a: entry({ sinceBaseline: { ...entry().sinceBaseline, scope: SCOPE_ALL }, all: { majorsDelta: -2, types: { closed: [], opened: [] } } }) });
  assert.equal(s.newCount, 2);
});

test('mixed baselines are reported, not hidden', () => {
  const s = sumSinceBaseline({ a: entry(), b: entry({ againstRunId: 'r1', againstCommitSha: 'def' }) });
  assert.deepEqual(s.againstRunIds, ['r0', 'r1']);
  assert.equal(s.scope, SCOPE_MIXED);
  assert.equal(s.changedFiles, null);
  assert.equal(s.majorsDelta, -4);
});

test('filterSinceBaseline keeps only the named dimensions, case-insensitively', () => {
  const kept = filterSinceBaseline({ Maintainability: entry(), security: entry() }, ['maintainability']);
  assert.deepEqual(Object.keys(kept), ['Maintainability']);
  assert.deepEqual(filterSinceBaseline(undefined, ['x']), {});
});

test('sinceBaselineFor gives the dimension entry only for the run the summary describes', () => {
  const map = { maintainability: entry() };
  assert.equal(sinceBaselineFor(map, 'Maintainability', { runId: 'r1', baselineRunId: 'r1' }), map.maintainability);
  assert.equal(sinceBaselineFor(map, 'maintainability', { runId: 'r0', baselineRunId: 'r1' }), undefined);
  assert.equal(sinceBaselineFor(map, 'maintainability', { runId: undefined, baselineRunId: 'r1' }), undefined);
  assert.equal(sinceBaselineFor(undefined, 'maintainability', { runId: 'r1', baselineRunId: 'r1' }), undefined);
});

test('dimensionHeadlineInput shapes the dimension page data for buildHeadline', () => {
  const input = dimensionHeadlineInput([{ req: 'A', severity: 'major' }, { req: 'B', severity: 'minor' }], { critical: 0, major: 1, minor: 1 }, { filesRead: 50, sourceFileCount: 100 });
  const h = buildHeadline([input]);
  assert.deepEqual([h.majors, h.critical, h.openTypes, h.violations, h.density, h.coveragePct], [1, 0, 2, 2, 4, 50]);
  assert.equal(buildHeadline([dimensionHeadlineInput([], { critical: 0, major: 0, minor: 0 }, {})]).density, null);
});

test('runCounts sums dimensionDetails and ignores the top-level totals when details exist', () => {
  const row = { majors: 99, openTypes: 99, critical: 99, dimensionDetails: [{ critical: 1, majors: 2, openTypes: 5 }, { critical: 0, majors: 1, openTypes: 4 }] };
  assert.deepEqual(runCounts(row), { critical: 1, majors: 3, openTypes: 9 });
});

test('runCounts falls back to the top-level totals only when there are no details at all', () => {
  assert.deepEqual(runCounts({ majors: 4, openTypes: 7 }), { critical: null, majors: 4, openTypes: 7 });
  // Details emptied by the visible-standards filter: the row's own totals
  // would count hidden standards, so nothing is shown.
  assert.deepEqual(runCounts({ critical: 4, majors: 9, openTypes: 7, dimensionDetails: [] }), { critical: null, majors: null, openTypes: null });
  assert.deepEqual(runCounts({ dimensionDetails: [{ majors: 2, openTypes: 3 }] }), { critical: null, majors: 2, openTypes: 3 });
  assert.deepEqual(runCounts({ dimensionDetails: [{ score: '7.0' }] }), { critical: null, majors: null, openTypes: null });
  assert.deepEqual(runCounts({}), { critical: null, majors: null, openTypes: null });
});

test('sumSinceBaseline folds criticalDelta, absent counting as 0', () => {
  const withDelta = (delta) => ({ againstRunId: 'r0', sinceBaseline: { scope: SCOPE_ALL, majorsDelta: 0, criticalDelta: delta, counts: {}, types: {} }, all: { majorsDelta: 0, criticalDelta: delta, counts: {}, types: {} } });
  assert.equal(sumSinceBaseline({ a: withDelta(1), b: withDelta(-2) }).criticalDelta, -1);
  assert.equal(sumSinceBaseline({ a: withDelta(undefined) }).criticalDelta, 0);
});

test('chipDeltas splits the blocking delta into criticals and majors only', () => {
  assert.deepEqual(chipDeltas({ majorsDelta: -83, criticalDelta: -1 }), { critical: -1, major: -82 });
  assert.deepEqual(chipDeltas({ majorsDelta: 2, criticalDelta: 3 }), { critical: 3, major: -1 });
  assert.equal(chipDeltas(null), null);
});

const row = (runId, details) => ({ runId, numericAverage: '7.0', dimensionDetails: details });
const det = (dimension, critical, majors) => ({ dimension, critical, majors });

test('periodChipDeltas compares the selected period row with the previous one, criticals taken out of majors', () => {
  const trend = [
    row('r2', [det('a', 2, 10), det('b', 0, 5)]),
    row('r1', [det('a', 1, 12), det('b', 0, 5)]),
    row('r0', [det('a', 9, 90)]),
  ];
  assert.deepEqual(periodChipDeltas(trend, 'r2'), { critical: 1, major: -3 });
  assert.deepEqual(periodChipDeltas(trend, null), { critical: 1, major: -3 });
  assert.deepEqual(periodChipDeltas(trend, 'r1'), { critical: -8, major: -70 });
});

test('periodChipDeltas counts the dimensions both rows scored only', () => {
  const trend = [row('r1', [det('a', 1, 3), det('b', 4, 8)]), row('r0', [det('a', 0, 2), det('c', 7, 7)])];
  assert.deepEqual(periodChipDeltas(trend, 'r1'), { critical: 1, major: 0 });
});

test('periodChipDeltas is null with no previous period, no shared dimension, or an unknown run', () => {
  assert.equal(periodChipDeltas([row('r1', [det('a', 1, 3)])], 'r1'), null);
  assert.equal(periodChipDeltas([row('r1', [det('a', 1, 3)]), row('r0', [det('b', 1, 3)])], 'r1'), null);
  assert.equal(periodChipDeltas([row('r1', [det('a', 1, 3)]), row('r0', [det('a', 1, 3)])], 'rX'), null);
  assert.equal(periodChipDeltas([], 'r1'), null);
  assert.equal(periodChipDeltas(undefined, 'r1'), null);
});

test('periodChipDeltas skips a dimension whose row lacks a count', () => {
  const trend = [row('r1', [det('a', 1, 3), { dimension: 'b', majors: 8 }]), row('r0', [det('a', 0, 2), det('b', 4, 8)])];
  assert.deepEqual(periodChipDeltas(trend, 'r1'), { critical: 1, major: 0 });
});
