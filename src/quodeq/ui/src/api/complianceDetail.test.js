import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  attachComplianceDetailRefs, groupDeferredCompliance, mergeComplianceDetail,
} from './complianceDetail.js';

const slim = (file, line, principle, extra = {}) => ({
  file, line, endLine: null, principle, title: `${principle} ok`,
  reason: null, snippet: null, context: null, detailDeferred: true, ...extra,
});
const full = (file, line, principle, extra = {}) => ({
  ...slim(file, line, principle), detailDeferred: false,
  reason: `why ${file}:${line}`, snippet: `code ${file}:${line}`, context: `ctx ${file}:${line}`, ...extra,
});

function scoresPayload() {
  return {
    accumulated: {
      dimensions: [
        { dimension: 'security', compliance: [slim('src/a.py', 1, 'P1'), slim('src/b.py', 2, 'P1')] },
        { dimension: 'usability', compliance: [{ ...full('x.py', 1, 'U1'), detailDeferred: false }] },
      ],
    },
  };
}

test('attach: deferred items get one shared ref per dimension', () => {
  const data = attachComplianceDetailRefs(scoresPayload(), 'proj', 'run-3', 7);
  const [a, b] = data.accumulated.dimensions[0].compliance;
  assert.deepEqual(a.detailRef, { project: 'proj', asOf: 'run-3', dimension: 'security', generation: 7 });
  assert.equal(a.detailRef, b.detailRef);
});

test('attach: items that already carry detail are left alone', () => {
  const data = attachComplianceDetailRefs(scoresPayload(), 'proj', null, 1);
  assert.equal(data.accumulated.dimensions[1].compliance[0].detailRef, undefined);
});

test('attach: tolerates a payload with no accumulated dimensions', () => {
  assert.deepEqual(attachComplianceDetailRefs({}, 'proj', null, 1), {});
});

test('group: narrows to the shared principle and common path prefix', () => {
  const data = attachComplianceDetailRefs(scoresPayload(), 'proj', null, 1);
  const groups = groupDeferredCompliance(data.accumulated.dimensions[0].compliance);
  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].scope, { principle: 'P1', pathPrefix: 'src/' });
});

test('group: mixed principles and unrelated paths drop the filters', () => {
  const ref = { project: 'p', asOf: null, dimension: 'd', generation: 1 };
  const groups = groupDeferredCompliance([
    { ...slim('a.py', 1, 'P1'), detailRef: ref },
    { ...slim('b.py', 2, 'P2'), detailRef: ref },
  ]);
  assert.deepEqual(groups[0].scope, { principle: undefined, pathPrefix: undefined });
});

test('group: nothing deferred means nothing to fetch', () => {
  assert.deepEqual(groupDeferredCompliance([full('a.py', 1, 'P1')]), []);
  assert.deepEqual(groupDeferredCompliance(undefined), []);
});

test('merge: fills detail by identity and keeps everything else', () => {
  const ref = { project: 'p', asOf: null, dimension: 'security', generation: 1 };
  const items = [{ ...slim('src/b.py', 2, 'P1'), detailRef: ref, dimension: 'security' }];
  const merged = mergeComplianceDetail(items, [{ ref, items: [full('src/a.py', 1, 'P1'), full('src/b.py', 2, 'P1')] }]);
  assert.equal(merged[0].snippet, 'code src/b.py:2');
  assert.equal(merged[0].reason, 'why src/b.py:2');
  assert.equal(merged[0].context, 'ctx src/b.py:2');
  assert.equal(merged[0].detailDeferred, false);
  assert.equal(merged[0].dimension, 'security');
});

test('merge: same-identity items get their details in order', () => {
  const ref = { project: 'p', asOf: null, dimension: 'd', generation: 1 };
  const items = [{ ...slim('a.py', 1, 'P1'), detailRef: ref }, { ...slim('a.py', 1, 'P1'), detailRef: ref }];
  const merged = mergeComplianceDetail(items, [{
    ref, items: [full('a.py', 1, 'P1', { reason: 'first' }), full('a.py', 1, 'P1', { reason: 'second' })],
  }]);
  assert.deepEqual(merged.map((m) => m.reason), ['first', 'second']);
});

test('merge: an item with no match stays as it was', () => {
  const ref = { project: 'p', asOf: null, dimension: 'd', generation: 1 };
  const item = { ...slim('gone.py', 1, 'P1'), detailRef: ref };
  const merged = mergeComplianceDetail([item], [{ ref, items: [] }]);
  assert.equal(merged[0], item);
});

test('merge: nothing loaded returns the same array', () => {
  const items = [slim('a.py', 1, 'P1')];
  assert.equal(mergeComplianceDetail(items, []), items);
});
