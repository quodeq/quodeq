import test from 'node:test';
import assert from 'node:assert/strict';
import {
  normalizeSeverity, summaryBucket, countBySeverity, emptySeverityCounts, sumSeverityTallies,
  countKnownSeverities, emptySeverityLists, severityListCounts,
} from './severity.js';

test('normalizeSeverity maps missing/invalid to unknown, known pass through', () => {
  assert.equal(normalizeSeverity('critical'), 'critical');
  assert.equal(normalizeSeverity('MAJOR'), 'major');
  assert.equal(normalizeSeverity(''), 'unknown');
  assert.equal(normalizeSeverity(null), 'unknown');
  assert.equal(normalizeSeverity('bogus'), 'unknown');
});

test('summaryBucket folds unknown into minor so chips sum to the total', () => {
  assert.equal(summaryBucket('critical'), 'critical');
  assert.equal(summaryBucket(null), 'minor');
  assert.equal(summaryBucket('bogus'), 'minor');
});

test('countBySeverity counts every violation exactly once', () => {
  const counts = countBySeverity([
    { severity: 'critical' },
    { severity: 'major' },
    { severity: 'minor' },
    { severity: null },
    { severity: 'weird' },
    {},
  ]);
  assert.deepEqual(counts, { critical: 1, major: 1, minor: 4 });
  assert.equal(counts.critical + counts.major + counts.minor, 6);
});

test('emptySeverityCounts returns a fresh zeroed tally each call', () => {
  const a = emptySeverityCounts();
  assert.deepEqual(a, { critical: 0, major: 0, minor: 0 });
  a.critical = 3;
  assert.deepEqual(emptySeverityCounts(), { critical: 0, major: 0, minor: 0 });
});

test('sumSeverityTallies adds every item severity and treats gaps as zero', () => {
  assert.deepEqual(sumSeverityTallies([]), { critical: 0, major: 0, minor: 0 });
  assert.deepEqual(
    sumSeverityTallies([
      { severity: { critical: 1, major: 2, minor: 3 } },
      { severity: { major: 1 } },
      { severity: null },
      {},
    ]),
    { critical: 1, major: 3, minor: 3 },
  );
});

test('countKnownSeverities counts a missing severity as minor and skips unlisted ones', () => {
  const vs = [{ severity: 'critical' }, {}, { severity: 'unknown' }, { severity: 'Major' }, { severity: 'major' }];
  assert.deepEqual(countKnownSeverities(vs), { critical: 1, major: 1, minor: 1 });
});

test('countKnownSeverities with ignoreCase lower-cases each severity first', () => {
  assert.deepEqual(countKnownSeverities([{ severity: 'Major' }, { severity: 'CRITICAL' }], { ignoreCase: true }), { critical: 1, major: 1, minor: 0 });
});

test('countKnownSeverities treats a missing list as empty', () => {
  assert.deepEqual(countKnownSeverities(undefined), { critical: 0, major: 0, minor: 0 });
});

test('emptySeverityLists gives a fresh empty list per display bucket, unknown included', () => {
  const a = emptySeverityLists();
  a.critical.push(1);
  assert.deepEqual([Object.keys(a), emptySeverityLists().critical], [['critical', 'major', 'minor', 'unknown'], []]);
});

test('severityListCounts gives each display bucket its list length', () => {
  assert.deepEqual(severityListCounts({ critical: [1, 2], major: [], minor: [3], unknown: [4] }), { critical: 2, major: 0, minor: 1, unknown: 1 });
});
