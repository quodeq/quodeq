import test from 'node:test';
import assert from 'node:assert/strict';
import { computeSummaryFromDimensions } from './visibleStandardsSummary.js';

test('computeSummaryFromDimensions: zeroes for an empty list', () => {
  assert.deepEqual(computeSummaryFromDimensions([]), {
    totalViolations: 0,
    totalCompliance: 0,
    severity: { critical: 0, major: 0, minor: 0 },
  });
});

test('computeSummaryFromDimensions: sums violations, compliance and severities across dimensions', () => {
  const dimensions = [
    {
      violations: [{ severity: 'critical' }, { severity: 'major' }],
      compliance: [{}, {}, {}],
    },
    {
      violations: [{ severity: 'minor' }, { severity: 'major' }],
      compliance: [{}],
    },
  ];
  assert.deepEqual(computeSummaryFromDimensions(dimensions), {
    totalViolations: 4,
    totalCompliance: 4,
    severity: { critical: 1, major: 2, minor: 1 },
  });
});

test('computeSummaryFromDimensions: treats missing violations/compliance as empty', () => {
  assert.deepEqual(computeSummaryFromDimensions([{}, { violations: null }]), {
    totalViolations: 0,
    totalCompliance: 0,
    severity: { critical: 0, major: 0, minor: 0 },
  });
});

test('computeSummaryFromDimensions: folds unknown severities into minor so the chips sum to the total', () => {
  const summary = computeSummaryFromDimensions([
    { violations: [{ severity: 'bogus' }, { severity: null }, {}] },
  ]);
  assert.equal(summary.totalViolations, 3);
  assert.deepEqual(summary.severity, { critical: 0, major: 0, minor: 3 });
});
