import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  attachComplianceDetailRefs, groupDeferredCompliance,
  attachFindingDetailRefs, attachRunFindingDetailRefs,
  pageSelector, replaceWithDetail, missingFromDetail, markDetailUnavailable,
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

test('attach: deferred items get one shared ref per dimension, naming content only', () => {
  const data = attachComplianceDetailRefs(scoresPayload(), 'proj', 'run-3');
  const [a, b] = data.accumulated.dimensions[0].compliance;
  assert.deepEqual(a.detailRef, { project: 'proj', asOf: 'run-3', dimension: 'security', kind: 'compliance' });
  assert.equal(a.detailRef, b.detailRef);
});

test('attach: two responses for the same content get equal refs', () => {
  const first = attachComplianceDetailRefs(scoresPayload(), 'proj', null).accumulated.dimensions[0].compliance[0].detailRef;
  const second = attachComplianceDetailRefs(scoresPayload(), 'proj', null).accumulated.dimensions[0].compliance[0].detailRef;
  assert.deepEqual(first, second);
  const run = attachRunFindingDetailRefs({ dimensions: [{ dimension: 'd', violations: [slim('a.py', 1, 'P1')] }] }, 'proj', 'r1');
  assert.deepEqual(run.dimensions[0].violations[0].detailRef, { project: 'proj', run: 'r1', dimension: 'd', kind: 'violation', source: 'local' });
});

test('attach: deferred violations get a violation-kind ref of their own', () => {
  const data = { accumulated: { dimensions: [{
    dimension: 'security',
    violations: [{ file: 'a.py', line: 1, principle: 'P1', title: 'v', detailDeferred: true }],
    compliance: [slim('b.py', 2, 'P1')],
  }] } };
  attachFindingDetailRefs(data, 'proj', null);
  const [dim] = data.accumulated.dimensions;
  assert.equal(dim.violations[0].detailRef.kind, 'violation');
  assert.equal(dim.compliance[0].detailRef.kind, 'compliance');
  assert.notEqual(dim.violations[0].detailRef, dim.compliance[0].detailRef);
});

test('attach: items that already carry detail are left alone', () => {
  const data = attachComplianceDetailRefs(scoresPayload(), 'proj', null);
  assert.equal(data.accumulated.dimensions[1].compliance[0].detailRef, undefined);
});

test('attach: tolerates a payload with no accumulated dimensions', () => {
  assert.deepEqual(attachComplianceDetailRefs({}, 'proj', null), {});
});

test('group: narrows to the shared principle and common path prefix, and keeps its items', () => {
  const data = attachComplianceDetailRefs(scoresPayload(), 'proj', null);
  const groups = groupDeferredCompliance(data.accumulated.dimensions[0].compliance);
  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].scope, { principle: 'P1', pathPrefix: 'src/' });
  assert.equal(groups[0].items.length, 2);
});

test('group: mixed principles and unrelated paths drop the filters', () => {
  const ref = { project: 'p', asOf: null, dimension: 'd' };
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

// The page's items say which of the server's rows belong on it: the fields
// they all agree on. One file is the File page, one principle the Principle
// page, one type a by-type file; a dimension's synthetic file agrees on none.
test('selector: keeps the rows matching every field the items are unanimous on', () => {
  const select = pageSelector([slim('src/a.py', 1, 'P1'), slim('src/a.py', 9, 'P2')]);
  assert.equal(select(full('src/a.py', 3, 'P3')), true);
  assert.equal(select(full('src/a.py.bak', 3, 'P1')), false);
  const byPrinciple = pageSelector([slim('a.py', 1, 'P1'), slim('b.py', 2, 'P1')]);
  assert.equal(byPrinciple(full('c.py', 1, 'P1')), true);
  assert.equal(byPrinciple(full('a.py', 1, 'P2')), false);
});

test('selector: a requirement\'s file keeps only that code, whatever its paths share', () => {
  // A by-type file opened from Fix first: the items carry no principle, only
  // their code. Without the code the shared path prefix let every other
  // requirement under it onto the page.
  const select = pageSelector([
    slim('src/a/x.py', 1, undefined, { req: 'R-1' }),
    slim('src/b/y.py', 2, undefined, { req: 'R-1' }),
  ]);
  assert.equal(select(full('src/c/z.py', 3, undefined, { req: 'R-1' })), true);
  assert.equal(select(full('src/a/x.py', 9, undefined, { req: 'R-2' })), false);
});

test('selector: a folder\'s file keeps that folder, not its subfolders', () => {
  const select = pageSelector([slim('src/svc/a.py', 1, 'P1'), slim('src/svc/b.py', 2, 'P2')]);
  assert.equal(select(full('src/svc/c.py', 3, 'P3')), true);
  assert.equal(select(full('src/svc/sub/d.py', 4, 'P1')), false);
});

test('selector: items that agree on nothing take every row', () => {
  const select = pageSelector([slim('a.py', 1, 'P1'), slim('b.py', 2, 'P2')]);
  assert.equal(select(full('zzz.py', 1, 'P9')), true);
  assert.equal(pageSelector([])(full('a.py', 1, 'P1')), true);
});

test('replace: a loaded group becomes the server rows, in its first position', () => {
  const ref = { project: 'p', asOf: null, dimension: 'security' };
  const other = { ...full('x.py', 1, 'U1'), dimension: 'usability' };
  const items = [{ ...slim('src/a.py', 1, 'P1'), detailRef: ref }, other, { ...slim('src/b.py', 2, 'P1'), detailRef: ref }];
  const rows = [full('src/a.py', 1, 'P1'), full('src/b.py', 2, 'P1'), full('src/c.py', 3, 'P1')];
  const out = replaceWithDetail(items, [{ ref, items: rows }], () => true);
  assert.deepEqual(out.map((i) => i.file), ['src/a.py', 'src/b.py', 'src/c.py', 'x.py']);
  assert.equal(out[0].snippet, 'code src/a.py:1');
  assert.equal(out[0].detailDeferred, false);
  assert.equal(out[0].detailRef, ref);
  assert.equal(out[3], other);
});

test('replace: the selector keeps the rows that belong on the page', () => {
  const ref = { project: 'p', asOf: null, dimension: 'd' };
  const items = [{ ...slim('a.py', 1, 'P1'), detailRef: ref }];
  const out = replaceWithDetail(items, [{ ref, items: [full('a.py', 1, 'P1'), full('b.py', 2, 'P1')] }], (r) => r.file === 'a.py');
  assert.deepEqual(out.map((i) => i.file), ['a.py']);
});

test('replace: a changed finding shows as the server has it now', () => {
  const ref = { project: 'p', asOf: null, dimension: 'd' };
  const items = [{ ...slim('a.py', 10, 'P1', { title: 'Old title' }), detailRef: ref }];
  const out = replaceWithDetail(items, [{ ref, items: [full('a.py', 12, 'P1', { title: 'New title' })] }], () => true);
  assert.equal(out.length, 1);
  assert.equal(out[0].title, 'New title');
  assert.equal(out[0].line, 12);
});

test('replace: a group still loading keeps its deferred items', () => {
  const ref = { project: 'p', asOf: null, dimension: 'd' };
  const later = { ...ref, dimension: 'e' };
  const waiting = { ...slim('later.py', 2, 'P1'), detailRef: later };
  const out = replaceWithDetail([{ ...slim('a.py', 1, 'P1'), detailRef: ref }, waiting], [{ ref, items: [full('a.py', 1, 'P1')] }], () => true);
  assert.equal(out[1], waiting);
});

test('replace: nothing loaded returns the same array', () => {
  const items = [slim('a.py', 1, 'P1')];
  assert.equal(replaceWithDetail(items, [], () => true), items);
});

// The list payload the page was built from can fall behind the detail: a
// finding it names at a file and line the server no longer has there was
// re-reported, moved or suppressed since. The page then refreshes the
// payload; the detail already shows the server's rows.
test('drift: a deferred item with no row at its file and line is missing', () => {
  const ref = { project: 'p', asOf: null, dimension: 'd' };
  const items = [{ ...slim('a.py', 10, 'P1'), detailRef: ref }];
  assert.equal(missingFromDetail(items, [{ ref, items: [full('a.py', 12, 'P1')] }], () => true), true);
  assert.equal(missingFromDetail(items, [{ ref, items: [full('a.py', 10, 'P1', { title: 'Renamed' })] }], () => true), false);
});

test('drift: extra server rows and groups still loading are not drift', () => {
  const ref = { project: 'p', asOf: null, dimension: 'd' };
  const later = { ...ref, dimension: 'e' };
  const items = [{ ...slim('a.py', 1, 'P1'), detailRef: ref }, { ...slim('b.py', 2, 'P1'), detailRef: later }];
  assert.equal(missingFromDetail(items, [{ ref, items: [full('a.py', 1, 'P1'), full('c.py', 3, 'P1')] }], () => true), false);
  assert.equal(missingFromDetail(items, [], () => true), false);
});

test('unavailable: the items of a failed group leave the deferred state and say so', () => {
  const ref = { project: 'p', asOf: null, dimension: 'd' };
  const other = { ...ref, dimension: 'e' };
  const failed = { ...slim('a.py', 1, 'P1'), detailRef: ref };
  const waiting = { ...slim('b.py', 2, 'P1'), detailRef: other };
  const marked = markDetailUnavailable([failed, waiting], [ref]);
  assert.equal(marked[0].detailDeferred, false);
  assert.equal(marked[0].detailUnavailable, true);
  assert.equal(marked[1], waiting);
  assert.equal(markDetailUnavailable([waiting], []).length, 1);
});

test('deferred items are matched to their group by the ref content, not the ref object', () => {
  const ref = { project: 'p', asOf: null, dimension: 'security', kind: 'violation' };
  const again = { ...ref };
  const items = [slim('a.py', 1, 'P1', { detailRef: ref }), slim('b.py', 2, 'P1', { detailRef: again })];

  const groups = groupDeferredCompliance(items);
  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].items.map((i) => i.file), ['a.py', 'b.py']);

  const loaded = [{ ref: again, items: [{ ...items[0], reason: 'why', detailDeferred: false }] }];
  const out = replaceWithDetail(items, loaded, () => true);
  assert.deepEqual(out.map((i) => [i.file, i.detailDeferred]), [['a.py', false]]);
  assert.equal(missingFromDetail(items, loaded, () => true), true);
  assert.equal(markDetailUnavailable(items, [again])[1].detailUnavailable, true);
});
