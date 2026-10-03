import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createDashboard } from './dashboard.js';

test('createDashboard keeps sinceBaseline', () => {
  const since = { maintainability: { againstRunId: 'r0', all: { majorsDelta: -1, types: { closed: [], opened: [] } } } };
  const out = createDashboard({ dimensions: [], trend: [], sinceBaseline: since });
  assert.deepEqual(out.sinceBaseline, since);
});

test('createDashboard defaults sinceBaseline to an empty object', () => {
  assert.deepEqual(createDashboard({ dimensions: [], trend: [] }).sinceBaseline, {});
});

test('createDashboard keeps a slim dimension slim (absent bodies stay absent)', () => {
  const d = createDashboard({ dimensions: [{ dimension: 'security', overallScore: '9.0', openTypes: 3 }], trend: [] });
  assert.equal(d.dimensions[0].violations, undefined);
  assert.equal(d.dimensions[0].compliance, undefined);
});

test('createDashboard still coerces a full dimension the old way', () => {
  const d = createDashboard({ dimensions: [{ dimension: 'security', violations: [{ file: 'a.py' }] }], trend: [] });
  assert.deepEqual(d.dimensions[0].compliance, []);
});

test('createDashboard passes a null dimension entry through unchanged', () => {
  const d = createDashboard({ dimensions: [null, { dimension: 'security' }], trend: [] });
  assert.equal(d.dimensions[0], null);
  assert.equal(d.dimensions[1].dimension, 'security');
});

test('createDashboard defaults an absent trend to an empty array', () => {
  assert.deepEqual(createDashboard({ dimensions: [] }).trend, []);
});
