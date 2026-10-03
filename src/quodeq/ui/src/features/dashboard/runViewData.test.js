import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRunViewData, withRunFindings } from './runViewData.js';

test('buildRunViewData: an unloaded dashboard yields empty view data', () => {
  const view = buildRunViewData(undefined);
  assert.deepEqual(view.runTopFiles, []);
  assert.equal(view.runSummary.totalViolations, 0);
  assert.equal(view.since, null);
  assert.equal(typeof view.headline, 'object');
});

test('buildRunViewData: worst files come from the run findings and carry the joined dimension names', () => {
  const dashboard = {
    dimensions: [
      { dimension: 'security', totals: { violationCount: 1 } },
      { dimension: 'maintainability', totals: { violationCount: 1 } },
    ],
  };
  const findings = [
    { dimension: 'security', violations: [{ file: 'a.py', severity: 'major' }] },
    { dimension: 'maintainability', violations: [{ file: 'a.py', severity: 'minor' }] },
  ];
  const view = buildRunViewData(dashboard, findings);
  assert.equal(view.runTopFiles.length, 1);
  assert.equal(view.runTopFiles[0].file, 'a.py');
  assert.equal(view.runTopFiles[0].dimensionsStr, 'maintainability, security');
  assert.equal(view.runSummary.dimensionCount, 2);
});

test('buildRunViewData: no worst files until the findings load', () => {
  const dashboard = { dimensions: [{ dimension: 'security', totals: { violationCount: 3 } }] };
  const view = buildRunViewData(dashboard);
  assert.deepEqual(view.runTopFiles, []);
  assert.equal(view.runSummary.totalViolations, 3);
  assert.equal(view.dimensions[0].violations, undefined);
});

test('withRunFindings: keeps the dashboard scalars and takes the lists by dimension name', () => {
  const dims = [{ dimension: 'Security', overallScore: '7.0', totals: { violationCount: 1 } }, { dimension: 'reliability' }];
  const findings = [{ dimension: 'security', overallScore: '7.0', violations: [{ file: 'a.py' }], compliance: [] }];
  const merged = withRunFindings(dims, findings);
  assert.equal(merged[0].overallScore, '7.0');
  assert.deepEqual(merged[0].violations, [{ file: 'a.py' }]);
  assert.deepEqual(merged[0].compliance, []);
  assert.equal(merged[1], dims[1]);
});
