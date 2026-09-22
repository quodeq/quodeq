import test from 'node:test';
import assert from 'node:assert/strict';
import { buildDimensionView, buildDimensionAttention } from './compareDimensionView.js';

function row(id, name, dim) {
  return { id, name, dims: [dim] };
}

test('buildDimensionView: does not throw and summarizes severity as zero when a dim has no severity object', () => {
  const rows = [
    row('p1', 'Project One', {
      key: 'clean-arch', label: 'Clean Architecture', score: 8,
      violations: 2, compliance: 5, principles: [],
      fromRunId: 'r1', name: 'clean-arch', fromDateLabel: '2026-01-01',
      // severity intentionally omitted
    }),
    row('p2', 'Project Two', {
      key: 'clean-arch', label: 'Clean Architecture', score: 6,
      violations: 1, compliance: 2, principles: [],
      fromRunId: 'r2', name: 'clean-arch', fromDateLabel: '2026-01-02',
      severity: { critical: 1, major: 0, minor: 2 },
    }),
  ];

  let view;
  assert.doesNotThrow(() => { view = buildDimensionView('clean-arch', rows, new Date(), {}); });
  // Only the second row supplied a severity object; the first contributes 0s.
  assert.deepEqual(view.severity, { critical: 1, major: 0, minor: 2 });
});

test('buildDimensionAttention: returns [] for a null view instead of throwing', () => {
  assert.deepEqual(buildDimensionAttention(null), []);
});
