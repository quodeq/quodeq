import test from 'node:test';
import assert from 'node:assert/strict';
import { buildFileTree } from '../viz/core/fileTree.js';

test('buildFileTree returns root node with empty dimensions', () => {
  const tree = buildFileTree([]);
  assert.equal(tree.name, '/');
  assert.equal(tree.violations, 0);
  assert.equal(tree.compliance, 0);
  assert.deepEqual(tree.children, []);
});

test('buildFileTree groups violations by folder', () => {
  const dimensions = [{
    dimension: 'Security',
    violations: [
      { file: 'src/auth/login.py', severity: 'critical', principle: 'P1', title: 'SQL injection' },
      { file: 'src/auth/login.py', severity: 'major', principle: 'P2', title: 'Weak hash' },
      { file: 'src/api/routes.py', severity: 'minor', principle: 'P3', title: 'Missing header' },
    ],
    compliance: [
      { file: 'src/auth/login.py', principle: 'P4', title: 'Input validated' },
    ],
  }];
  const tree = buildFileTree(dimensions);
  assert.equal(tree.violations, 3);
  assert.equal(tree.compliance, 1);
  assert.equal(tree.children.length, 1); // src/
  const src = tree.children[0];
  assert.equal(src.name, 'src');
  assert.equal(src.children.length, 2); // auth/, api/
});

test('buildFileTree calculates severity breakdown', () => {
  const dimensions = [{
    dimension: 'Security',
    violations: [
      { file: 'a.py', severity: 'critical' },
      { file: 'a.py', severity: 'major' },
      { file: 'b.py', severity: 'minor' },
    ],
    compliance: [],
  }];
  const tree = buildFileTree(dimensions);
  assert.equal(tree.severity.critical, 1);
  assert.equal(tree.severity.major, 1);
  assert.equal(tree.severity.minor, 1);
});

test('buildFileTree calculates complianceRate', () => {
  const dimensions = [{
    dimension: 'Security',
    violations: [{ file: 'a.py', severity: 'minor' }],
    compliance: [{ file: 'a.py' }, { file: 'a.py' }, { file: 'a.py' }],
  }];
  const tree = buildFileTree(dimensions);
  assert.equal(tree.complianceRate, 0.75);
});

test('buildFileTree tracks per-dimension breakdown', () => {
  const dimensions = [
    { dimension: 'Security', violations: [{ file: 'a.py', severity: 'critical' }], compliance: [{ file: 'a.py' }] },
    { dimension: 'Performance', violations: [], compliance: [{ file: 'a.py' }] },
  ];
  const tree = buildFileTree(dimensions);
  const fileNode = tree.children[0]; // a.py
  assert.equal(fileNode.dimensions.Security.violations, 1);
  assert.equal(fileNode.dimensions.Security.compliance, 1);
  assert.equal(fileNode.dimensions.Performance.violations, 0);
  assert.equal(fileNode.dimensions.Performance.compliance, 1);
});

test('buildFileTree handles null/missing file paths', () => {
  const dimensions = [{
    dimension: 'Security',
    violations: [{ file: null, severity: 'minor' }, { severity: 'major' }],
    compliance: [],
  }];
  const tree = buildFileTree(dimensions);
  assert.equal(tree.violations, 2);
});

test('buildFileTree sorts children by violation count descending', () => {
  const dimensions = [{
    dimension: 'Security',
    violations: [
      { file: 'b.py', severity: 'minor' },
      { file: 'a.py', severity: 'critical' },
      { file: 'a.py', severity: 'major' },
    ],
    compliance: [],
  }];
  const tree = buildFileTree(dimensions);
  assert.equal(tree.children[0].name, 'a.py');
  assert.equal(tree.children[1].name, 'b.py');
});
