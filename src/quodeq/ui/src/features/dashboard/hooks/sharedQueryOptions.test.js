import test from 'node:test';
import assert from 'node:assert/strict';
import { SUMMARY_POLL_MS, sharedListQueryOptions } from './sharedQueryOptions.js';
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

test('list query: re-lists while the server is still warming cards it has not shown yet', () => {
  const on = sharedListQueryOptions({ sharedListProjects: () => 'list', configured: true });
  const query = (data) => ({ state: { data, error: null } });
  assert.equal(on.refetchInterval(query({ projects: [], warmup: { active: true, projectsDone: 0, projectsTotal: 3 } })), SUMMARY_POLL_MS);
  assert.equal(on.refetchInterval(query({ projects: [{ id: 'a' }], warmup: { active: false, projectsDone: 3, projectsTotal: 3 } })), false);
  assert.equal(on.refetchInterval(query({ projects: [{ id: 'a', summaryPending: true }] })), SUMMARY_POLL_MS);
  assert.equal(on.refetchInterval(query({ projects: [{ id: 'a' }] })), false);
  assert.equal(on.refetchInterval(query(undefined)), false);
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
