import test from 'node:test';
import assert from 'node:assert/strict';
import { computeLevelInfo } from './packLevelInfo.js';

function node(data, { parent = null } = {}) {
  return { data, parent };
}

test('computeLevelInfo: returns null without a focus node', () => {
  assert.equal(computeLevelInfo(null, null, () => {}), null);
});

test('computeLevelInfo: folder lines use the shared localised builder with coloured severities', () => {
  const root = node({ name: '/', violations: 0, compliance: 0, children: [] });
  const focus = node({
    name: 'src', violations: 3, compliance: 6,
    severity: { critical: 0, major: 1, minor: 2 },
    children: [{ isFile: true }, { children: [{ isFile: true }] }],
  }, { parent: root });
  const info = computeLevelInfo(focus, root, () => {});
  assert.equal(info.title, 'src');
  assert.deepEqual(info.lines, [
    { label: 'Compliance', value: '67%' },
    { label: 'Contents', value: 2 },
    { label: 'Violations', value: 3 },
    { label: 'Major', value: 1, color: 'var(--color-sev-major-text)' },
    { label: 'Minor', value: 2, color: 'var(--color-sev-minor-text)' },
  ]);
  assert.equal(typeof info.detailAction, 'function');
});

test('computeLevelInfo: a level with nothing checked shows a dash for compliance', () => {
  const root = node({ name: '/', violations: 0, compliance: 0, children: [] });
  const info = computeLevelInfo(root, root, () => {});
  assert.equal(info.title, 'Project');
  assert.equal(info.lines[0].value, '—');
  assert.equal(info.detailAction, null);
});

test('computeLevelInfo: the detail action hands the node data to the click handler', () => {
  const root = node({ name: '/', violations: 0, compliance: 0 });
  const data = { name: 'pkg/mod', violations: 0, compliance: 1 };
  const clicked = [];
  const info = computeLevelInfo(node(data, { parent: root }), root, (d) => clicked.push(d));
  assert.equal(info.title, 'pkg');
  info.detailAction();
  assert.deepEqual(clicked, [data]);
});
