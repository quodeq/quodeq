import test from 'node:test';
import assert from 'node:assert/strict';
import { filterAccumulatedByVisibleStandards } from './scoreFiltering.js';

// The header SCORE normally uses the trend's accumulated average (to agree
// with the History chart). But for an all-cancelled project the trend is
// empty (cancelled runs aren't chart points), while the accumulated
// dimension cards DO show scores. Falling through to null there made the
// header read "—" over cards showing 6.0 — the same no-complete-run
// inconsistency this batch unifies. Fall back to the accumulated summary.

const ACC = {
  dimensions: [{ dimension: 'security', overallScore: '6.0/10', totals: { violationCount: 0, complianceCount: 0 } }],
  summary: { numericAverage: 6.0, overallGrade: 'Adequate' },
};
const VISIBLE = new Set(['security']);

test('empty trend: header number falls back to the accumulated summary', () => {
  const out = filterAccumulatedByVisibleStandards(ACC, VISIBLE, [], null);
  assert.equal(out.summary.numericAverage, 6.0);
});

test('populated trend still wins (unchanged behavior)', () => {
  const trend = [{ runId: 'r1', numericAverage: 8.2 }];
  const out = filterAccumulatedByVisibleStandards(ACC, VISIBLE, trend, 'r1');
  assert.equal(out.summary.numericAverage, 8.2);
});
