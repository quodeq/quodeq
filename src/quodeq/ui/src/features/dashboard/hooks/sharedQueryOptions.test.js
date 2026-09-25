import test from 'node:test';
import assert from 'node:assert/strict';
import { sharedStatusQueryOptions, sharedListQueryOptions } from './sharedQueryOptions.js';
import { sharedKeys } from '../../../api/queryKeys.js';

const getSharedStatus = async () => ({ configured: true });

test('status query: shared status key, no enabled flag unless one is given', () => {
  const opts = sharedStatusQueryOptions({ getSharedStatus });
  assert.deepEqual(opts.queryKey, sharedKeys.status());
  assert.equal(opts.queryFn, getSharedStatus);
  assert.equal('enabled' in opts, false);
  assert.equal('refetchOnWindowFocus' in opts, false);
  assert.equal(sharedStatusQueryOptions({ getSharedStatus, enabled: false }).enabled, false);
});

test('status query carries extra observer options', () => {
  const opts = sharedStatusQueryOptions({ getSharedStatus, observerOptions: { refetchOnWindowFocus: false } });
  assert.equal(opts.refetchOnWindowFocus, false);
});

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
