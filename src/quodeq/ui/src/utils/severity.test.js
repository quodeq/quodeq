import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeSeverity, summaryBucket, countBySeverity } from './severity.js';

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
