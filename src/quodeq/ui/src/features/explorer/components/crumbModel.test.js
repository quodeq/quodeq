import test from 'node:test';
import assert from 'node:assert/strict';
import { collapseCrumbs, isRunDateEntry } from './crumbModel.js';

const c = (label, index, extra = {}) => ({ label, index, ...extra });

test('short paths pass through untouched', () => {
  const crumbs = [c('repo', -1, { isProject: true }), c('overview', 0), c('maintainability', 1)];
  assert.deepEqual(collapseCrumbs(crumbs), crumbs);
});

test('deep paths keep root plus last two, collapse the middle', () => {
  const crumbs = [
    c('repo', -1, { isProject: true }),
    c('overview', 0),
    c('security', 1),
    c('maintainability', 2),
    c('modularity', 3),
  ];
  const out = collapseCrumbs(crumbs);
  assert.equal(out.length, 4);
  assert.equal(out[0].label, 'repo');
  assert.equal(out[1].ellipsis, true);
  assert.deepEqual(out[1].hidden.map((h) => h.label), ['overview', 'security']);
  assert.equal(out[2].label, 'maintainability');
  assert.equal(out[3].label, 'modularity');
});

test('intermediate run-date segments collapse even in short paths', () => {
  const crumbs = [
    c('repo', -1, { isProject: true }),
    c('history', 0),
    c('28 jul 2026', 1, { isRunDate: true }),
    c('maintainability', 2),
  ];
  const out = collapseCrumbs(crumbs);
  assert.deepEqual(out.map((s) => s.ellipsis ? '…' : s.label), ['repo', 'history', '…', 'maintainability']);
  assert.deepEqual(out[2].hidden.map((h) => h.label), ['28 jul 2026']);
});

test('a run-date segment that is the current page stays visible', () => {
  const crumbs = [
    c('repo', -1, { isProject: true }),
    c('history', 0),
    c('28 jul 2026', 1, { isRunDate: true }),
  ];
  assert.deepEqual(collapseCrumbs(crumbs), crumbs);
});

test('deep path with a run date merges everything into one ellipsis group', () => {
  const crumbs = [
    c('repo', -1, { isProject: true }),
    c('history', 0),
    c('28 jul 2026', 1, { isRunDate: true }),
    c('maintainability', 2),
    c('modularity', 3),
  ];
  const out = collapseCrumbs(crumbs);
  assert.deepEqual(out.map((s) => s.ellipsis ? '…' : s.label), ['repo', '…', 'maintainability', 'modularity']);
  assert.deepEqual(out[1].hidden.map((h) => h.label), ['history', '28 jul 2026']);
});

test('single crumb renders as-is', () => {
  const crumbs = [c('repo', -1, { isProject: true })];
  assert.deepEqual(collapseCrumbs(crumbs), crumbs);
});

test('isRunDateEntry matches run and history-run pages only', () => {
  assert.equal(isRunDateEntry({ page: 'run' }), true);
  assert.equal(isRunDateEntry({ page: 'history-run' }), true);
  assert.equal(isRunDateEntry({ page: 'explorer' }), false);
  assert.equal(isRunDateEntry(null), false);
});
