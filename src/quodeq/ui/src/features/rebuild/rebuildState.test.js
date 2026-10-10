import { test } from 'node:test';
import assert from 'node:assert/strict';
import { REBUILD_STATE, isBusyState, pickRebuildState, rebuildPercent, rebuildCopy } from './rebuildState.js';

const warming = { active: true, projectsDone: 2, projectsTotal: 12, currentProjectName: 'quodeq' };

test('pickRebuildState: a tracked pass with no runs listed yet is listing', () => {
  const state = pickRebuildState({ rescore: { state: 'running', done: 0, total: 0 }, tracking: true, warmup: warming });
  assert.equal(state.kind, REBUILD_STATE.LISTING);
  assert.equal(rebuildPercent(state), null);
});

test('pickRebuildState: a tracked pass with counts is rescoring and wins over the warm-up', () => {
  const state = pickRebuildState({ rescore: { state: 'running', done: 412, total: 1980 }, tracking: true, warmup: warming });
  assert.deepEqual(state, { kind: REBUILD_STATE.RESCORING, done: 412, total: 1980 });
  assert.equal(rebuildPercent(state), 21);
});

test('pickRebuildState: a pass that ended in error is failed until retried', () => {
  const state = pickRebuildState({ rescore: { state: 'error', done: 3, total: 9 }, tracking: false, warmup: null });
  assert.equal(state.kind, REBUILD_STATE.FAILED);
  assert.equal(rebuildPercent(state), null);
});

test('pickRebuildState: an active warm-up carries its counts and the current project', () => {
  const state = pickRebuildState({ rescore: undefined, tracking: false, warmup: warming });
  assert.deepEqual(state, { kind: REBUILD_STATE.WARMING, done: 2, total: 12, name: 'quodeq' });
  assert.equal(rebuildPercent(state), 17);
});

test('pickRebuildState: nothing running is idle', () => {
  assert.equal(pickRebuildState({ rescore: { state: 'idle' }, tracking: false, warmup: { active: false } }).kind, REBUILD_STATE.IDLE);
  assert.equal(pickRebuildState({ rescore: undefined, tracking: false, warmup: null }).kind, REBUILD_STATE.IDLE);
});

test('isBusyState: listing, rescoring and warming are busy; done, failed and idle are not', () => {
  assert.equal(isBusyState(REBUILD_STATE.LISTING), true);
  assert.equal(isBusyState(REBUILD_STATE.RESCORING), true);
  assert.equal(isBusyState(REBUILD_STATE.WARMING), true);
  assert.equal(isBusyState(REBUILD_STATE.DONE), false);
  assert.equal(isBusyState(REBUILD_STATE.FAILED), false);
  assert.equal(isBusyState(REBUILD_STATE.IDLE), false);
});

test('rebuildCopy: the row names the counts and the current project; the announcement carries no numbers', () => {
  const rescoring = rebuildCopy({ kind: REBUILD_STATE.RESCORING, done: 412, total: 1980 });
  assert.equal(rescoring.label, 'rescoring');
  assert.equal(rescoring.meta, '412 of 1980 runs…');
  assert.doesNotMatch(rescoring.announce, /\d/);
  const warmingCopy = rebuildCopy({ kind: REBUILD_STATE.WARMING, done: 2, total: 12, name: 'quodeq' });
  assert.equal(warmingCopy.meta, '2 of 12 projects · quodeq now…');
  assert.equal(rebuildCopy({ kind: REBUILD_STATE.WARMING, done: 2, total: 12, name: null }).meta, '2 of 12 projects…');
});

test('rebuildCopy: the done row says what finished; failed carries the old-formula warning', () => {
  assert.equal(rebuildCopy({ kind: REBUILD_STATE.DONE }, { kind: REBUILD_STATE.RESCORING, total: 1980 }).meta, '1980 runs rescored');
  assert.equal(rebuildCopy({ kind: REBUILD_STATE.DONE }, { kind: REBUILD_STATE.WARMING, total: 12 }).meta, '12 projects rebuilt');
  assert.equal(rebuildCopy({ kind: REBUILD_STATE.DONE }, null).meta, '');
  const failed = rebuildCopy({ kind: REBUILD_STATE.FAILED });
  assert.equal(failed.label, 'rescore failed');
  assert.match(failed.meta, /old formula/);
  assert.equal(rebuildCopy({ kind: REBUILD_STATE.IDLE }).label, '');
});
