import test from 'node:test';
import assert from 'node:assert/strict';
import { sharedListQueryOptions } from './sharedQueryOptions.js';
import { sharedKeys } from '../../../api/queryKeys.js';

test('list query: enabled only when configured and the caller gate allows it', () => {
  const calls = [];
  const sharedListProjects = (arg) => { calls.push(arg); return 'list'; };
  const on = sharedListQueryOptions({ sharedListProjects, configured: true });
  assert.deepEqual(on.queryKey, sharedKeys.list());
  assert.equal(on.enabled, true);
  assert.equal(on.queryFn(), 'list');
  assert.deepEqual(calls, [{ refresh: false }]);
  assert.equal(sharedListQueryOptions({ sharedListProjects, configured: false }).enabled, false);
  assert.equal(sharedListQueryOptions({ sharedListProjects, configured: true, enabled: false }).enabled, false);
  assert.equal(sharedListQueryOptions({ sharedListProjects, configured: true, enabled: true }).enabled, true);
  assert.equal('refetchOnWindowFocus' in on, false);
  assert.equal(
    sharedListQueryOptions({ sharedListProjects, configured: true, observerOptions: { refetchOnWindowFocus: false } }).refetchOnWindowFocus,
    false,
  );
});

test('list query: waits while a connect is active, never for a refresh or pull', () => {
  const sharedListProjects = () => 'list';
  const enabledFor = (status) => sharedListQueryOptions({ sharedListProjects, configured: true, status }).enabled;
  const slot = (phase) => ({ state: 'running', phase });
  assert.equal(enabledFor({ connect: slot('reading') }), false);
  assert.equal(enabledFor({ connect: slot('downloading') }), false);
  assert.equal(enabledFor({ connect: slot('connecting') }), false);
  assert.equal(enabledFor({ connect: { state: 'done', phase: 'done' } }), true);
  assert.equal(enabledFor({ refresh: slot('downloading') }), true);
  assert.equal(enabledFor({ pull: slot('reading') }), true);
  assert.equal(enabledFor({ connect: { state: 'idle', phase: null } }), true);
  assert.equal(enabledFor(undefined), true);
});
