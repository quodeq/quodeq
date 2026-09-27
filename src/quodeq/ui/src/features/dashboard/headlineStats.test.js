import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildHeadline, dimensionOpenTypes, formatDensity, filterSinceBaseline, reduceDiffToSinceMap, runCounts, sinceBaselineFor, sumSinceBaseline, SCOPE_ALL, SCOPE_CHANGED, SCOPE_MIXED } from './headlineStats.js';

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
  assert.equal(formatDensity(h.density), '-');
  assert.equal(formatDensity(32.34), '32.3');
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

test('runCounts sums dimensionDetails and ignores the top-level totals when details exist', () => {
  const entry = { majors: 99, openTypes: 99, dimensionDetails: [{ majors: 2, openTypes: 5 }, { majors: 1, openTypes: 4 }] };
  assert.deepEqual(runCounts(entry), { majors: 3, openTypes: 9 });
});

test('runCounts falls back to the top-level totals, then to null', () => {
  assert.deepEqual(runCounts({ majors: 4, openTypes: 7, dimensionDetails: [] }), { majors: 4, openTypes: 7 });
  assert.deepEqual(runCounts({ dimensionDetails: [{ score: '7.0' }] }), { majors: null, openTypes: null });
  assert.deepEqual(runCounts({}), { majors: null, openTypes: null });
});

test('reduceDiffToSinceMap gives the dashboard map shape', () => {
  const diff = { runId: 'r1', commitSha: 'abc', dimensions: { maintainability: {
    counts: { carried: 1, same: 2, moved: 0, new: 3, resolved: 4, notReevaluated: 0 }, majorsDelta: -1,
    types: { closed: ['M-A-1'], opened: [], perReq: {} }, againstRunId: 'r0', againstCommitSha: 'def',
    sinceBaseline: { scope: 'changed-files', changedFiles: 2, majorsDelta: -1, counts: { new: 1, resolved: 2 }, types: { closed: ['M-A-1'], opened: [] }, new: [], resolved: [] },
  } } };
  const map = reduceDiffToSinceMap(diff);
  assert.deepEqual(Object.keys(map), ['maintainability']);
  assert.equal(map.maintainability.againstRunId, 'r0');
  assert.deepEqual(map.maintainability.sinceBaseline, { scope: 'changed-files', changedFiles: 2, majorsDelta: -1, counts: { new: 1, resolved: 2 }, types: { closed: ['M-A-1'], opened: [] } });
  assert.deepEqual(map.maintainability.all, { majorsDelta: -1, counts: { new: 3, resolved: 4 }, types: { closed: ['M-A-1'], opened: [] } });
  assert.notEqual(sumSinceBaseline(map), null);
  assert.deepEqual(reduceDiffToSinceMap(null), {});
});
