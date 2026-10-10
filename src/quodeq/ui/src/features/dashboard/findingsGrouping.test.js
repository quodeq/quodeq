import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dirOf, sharedPrefix, groupByRequirement, groupByFolder, splitFolderLabel, folderDimensions } from './findingsGrouping.js';

const v = (file, req, severity, over = {}) => ({ file, req, severity, title: `${req} title`, principle: 'P', ...over });

test('dirOf returns the folder, empty for a root file', () => {
  assert.equal(dirOf('a/b/c.py'), 'a/b');
  assert.equal(dirOf('c.py'), '');
  assert.equal(dirOf(undefined), '');
});

test('sharedPrefix keeps the common lead and never a whole path', () => {
  assert.equal(sharedPrefix(['src/main/a', 'src/main/b/c']), 'src/main');
  assert.equal(sharedPrefix(['src/a', 'tools']), '');
  assert.equal(sharedPrefix(['src/a/b']), 'src/a');
  assert.equal(sharedPrefix(['src/a', 'src/a/b']), 'src');
  assert.equal(sharedPrefix([]), '');
});

test('groupByRequirement ranks critical, then major, then count', () => {
  const dims = [
    { dimension: 'security', violations: [v('a.py', 'S-1', 'minor'), v('a.py', 'S-1', 'minor'), v('a.py', 'S-1', 'minor'), v('b.py', 'S-2', 'major')] },
    { dimension: 'reliability', violations: [v('c.py', 'R-1', 'critical')] },
  ];
  const rows = groupByRequirement(dims);
  assert.deepEqual(rows.map((r) => r.req), ['R-1', 'S-2', 'S-1']);
  assert.equal(rows[2].count, 3);
  assert.equal(rows[2].fileCount, 1);
  assert.deepEqual(rows[2].sev, { critical: 0, major: 0, minor: 3 });
});

test('groupByRequirement keeps the same code in two dimensions apart and skips findings without one', () => {
  const dims = [
    { dimension: 'a', violations: [v('x.py', 'X-1', 'minor'), v('x.py', undefined, 'major')] },
    { dimension: 'b', violations: [v('y.py', 'X-1', 'minor')] },
  ];
  const rows = groupByRequirement(dims);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((r) => r.dimension).sort(), ['a', 'b']);
});

test('groupByRequirement names the row by its most frequent title', () => {
  const dims = [{ dimension: 'a', violations: [
    v('x.py', 'X-1', 'minor', { title: 'rare' }),
    v('x.py', 'X-1', 'minor', { title: 'common' }),
    v('y.py', 'X-1', 'minor', { title: 'common' }),
  ] }];
  assert.equal(groupByRequirement(dims)[0].text, 'common');
});

test('groupByFolder keeps same-named folders apart and drops the shared prefix', () => {
  const dims = [{ dimension: 'a', violations: [
    v('src/app/Article/Views/A.swift', 'X-1', 'major'),
    v('src/lib/Article/Views/B.swift', 'X-1', 'minor'),
    v('src/lib/Article/Views/C.swift', 'X-1', 'minor'),
  ] }];
  const { prefix, rows } = groupByFolder(dims);
  assert.equal(prefix, 'src');
  assert.deepEqual(rows.map((r) => r.label), ['app/Article/Views', 'lib/Article/Views']);
  assert.equal(rows[1].fileCount, 2);
  assert.equal(rows[0].dir, 'src/app/Article/Views');
});

test('splitFolderLabel mutes the lead and keeps the last two folders', () => {
  assert.deepEqual(splitFolderLabel('ui/src/features/dashboard/components'), { lead: 'ui/src/features/', tail: 'dashboard/components/' });
  assert.deepEqual(splitFolderLabel('tools'), { lead: '', tail: 'tools/' });
  assert.deepEqual(splitFolderLabel(''), { lead: '', tail: '' });
});

test('folderDimensions keeps only that folder\'s findings and checks, and drops dimensions without findings there', () => {
  const dims = [
    { dimension: 'a', violations: [v('src/x/a.py', 'X-1', 'minor'), v('src/y/b.py', 'X-1', 'minor')], compliance: [{ file: 'src/x/c.py' }, { file: 'src/y/d.py' }] },
    { dimension: 'b', violations: [v('src/y/c.py', 'Y-1', 'minor')] },
  ];
  const out = folderDimensions(dims, 'src/x');
  assert.equal(out.length, 1);
  assert.equal(out[0].violations.length, 1);
  assert.deepEqual(out[0].compliance, [{ file: 'src/x/c.py' }]);
});
