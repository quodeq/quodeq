import test from 'node:test';
import assert from 'node:assert/strict';
import { buildLevelInfo } from './galaxyFolderLevelInfo.js';

const noScene = { rootStars: [] };

function folderInfo(currentNode, { scene = noScene, isRoot = true } = {}) {
  return buildLevelInfo({
    scene,
    currentNode,
    zoomedFileRef: { current: null },
    navRef: { current: { path: isRoot ? [currentNode] : [currentNode, currentNode] } },
    projectName: 'Demo',
    onFileClick: () => {},
  });
}

function fileInfo(data) {
  return buildLevelInfo({
    scene: noScene,
    currentNode: null,
    zoomedFileRef: { current: { data } },
    navRef: { current: { path: [] } },
    projectName: 'Demo',
    onFileClick: () => {},
  });
}

test('buildLevelInfo: returns null without a scene', () => {
  assert.equal(buildLevelInfo({ scene: null, zoomedFileRef: { current: null } }), null);
});

test('buildLevelInfo: zoomed file lists only the non-zero severities, critical first', () => {
  const info = fileInfo({
    name: 'a.py', violations: 4, compliance: 1,
    severity: { critical: 1, major: 0, minor: 3 },
  });
  assert.equal(info.title, 'a.py');
  assert.deepEqual(info.lines, [
    { label: 'Violations', value: 4 },
    { label: 'Compliance', value: 1 },
    { label: 'Critical', value: 1 },
    { label: 'Minor', value: 3 },
  ]);
  assert.equal(info.hint, null);
});

test('buildLevelInfo: zoomed file with no severity block lists no severity lines', () => {
  const info = fileInfo({ name: 'a.py', violations: 0, compliance: 2 });
  assert.deepEqual(info.lines, [
    { label: 'Violations', value: 0 },
    { label: 'Compliance', value: 2 },
  ]);
});

test('buildLevelInfo: folder severity lines carry the severity color tokens', () => {
  const info = folderInfo({
    name: 'src', violations: 6, complianceRate: 0.5,
    severity: { critical: 2, major: 1, minor: 3 },
  });
  assert.deepEqual(info.lines, [
    { label: 'Compliance', value: '50%' },
    { label: 'Contents', value: 0 },
    { label: 'Violations', value: 6 },
    { label: 'Critical', value: 2, color: 'var(--color-sev-critical-text)' },
    { label: 'Major', value: 1, color: 'var(--color-sev-major-text)' },
    { label: 'Minor', value: 3, color: 'var(--color-sev-minor-text)' },
  ]);
});

test('buildLevelInfo: folder with no violations shows no severity lines', () => {
  const info = folderInfo({
    name: 'src', violations: 0, complianceRate: 1,
    severity: { critical: 0, major: 0, minor: 0 },
  });
  assert.deepEqual(info.lines, [
    { label: 'Compliance', value: '100%' },
    { label: 'Contents', value: 0 },
    { label: 'Violations', value: 0 },
  ]);
});

test('buildLevelInfo: root folder uses the project name, deeper levels the node name', () => {
  const node = { name: 'src', violations: 0, complianceRate: 1 };
  assert.equal(folderInfo(node).title, 'Demo');
  assert.equal(folderInfo(node).detailAction, null);
  const deep = folderInfo(node, { isRoot: false });
  assert.equal(deep.title, 'src');
  assert.equal(typeof deep.detailAction, 'function');
});

test('buildLevelInfo: folder hint appears only when the level holds folders', () => {
  const node = { name: 'src', violations: 0, complianceRate: 1 };
  const scene = { rootStars: [{ isFolder: true }, { isFolder: false }] };
  assert.equal(typeof folderInfo(node, { scene }).hint, 'string');
  assert.equal(folderInfo(node).hint, null);
});
