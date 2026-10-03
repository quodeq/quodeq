import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildTopOffendingFiles } from './explorerUtils.js';

// The worst-files table hands its rows to the File page, which hydrates the
// detail /scores deferred. The rows must keep what hydration needs: the
// ref, the marker and the identity fields.
test('buildTopOffendingFiles keeps the deferred-detail ref and identity on each row', () => {
  const ref = { project: 'p', asOf: null, dimension: 'security', generation: 1, kind: 'violation' };
  const dimensions = [{
    dimension: 'security',
    violations: [{
      file: 'src/a.py', line: 3, endLine: 5, principle: 'P1', title: 'Shell out', severity: 'major',
      reason: null, snippet: null, context: null, reqRefs: [], detailDeferred: true, detailRef: ref,
    }],
  }];
  const [row] = buildTopOffendingFiles(dimensions);
  const [v] = row.violationsBySeverity.major;
  assert.equal(v.detailRef, ref);
  assert.equal(v.detailDeferred, true);
  assert.equal(v.endLine, 5);
  assert.deepEqual(v.reqRefs, []);
  assert.equal(v.title, 'Shell out');
});
