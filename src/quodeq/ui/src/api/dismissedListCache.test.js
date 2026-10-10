import { test } from 'node:test';
import assert from 'node:assert/strict';
import { QueryClient } from '@tanstack/react-query';
import { dismissedEntryId, recordDismissedEntry } from './dismissedListCache.js';
import { projectKeys } from './queryKeys.js';

const A = { req: 'A1', file: 'a.py', line: 10, fingerprint: 'ab'.repeat(32) };
const B = { req: 'B1', file: 'b.py', line: 20, fingerprint: null };

test('dismissedEntryId names a fingerprinted entry by fingerprint and the rest by line', () => {
  assert.equal(dismissedEntryId(A), `A1|a.py|${'ab'.repeat(32)}`);
  assert.equal(dismissedEntryId(B), 'B1|b.py|line:20');
});

test('recordDismissedEntry prepends to a cached list once', () => {
  const qc = new QueryClient();
  qc.setQueryData(projectKeys.dismissed('p1', 'local'), [B]);

  recordDismissedEntry(qc, 'p1', 'local', A);
  recordDismissedEntry(qc, 'p1', 'local', { ...A, line: 99 });

  assert.deepEqual(qc.getQueryData(projectKeys.dismissed('p1', 'local')), [A, B]);
});

test('recordDismissedEntry leaves an uncached list alone, so the first open fetches it whole', () => {
  const qc = new QueryClient();

  recordDismissedEntry(qc, 'p1', 'local', A);
  recordDismissedEntry(qc, 'p1', 'local', undefined);
  recordDismissedEntry(qc, '', 'local', A);

  assert.equal(qc.getQueryData(projectKeys.dismissed('p1', 'local')), undefined);
});

test('recordDismissedEntry writes into the named project only', () => {
  const qc = new QueryClient();
  qc.setQueryData(projectKeys.dismissed('p1', 'local'), []);
  qc.setQueryData(projectKeys.dismissed('p2', 'local'), []);

  recordDismissedEntry(qc, 'p2', 'local', A);

  assert.deepEqual(qc.getQueryData(projectKeys.dismissed('p1', 'local')), []);
  assert.deepEqual(qc.getQueryData(projectKeys.dismissed('p2', 'local')), [A]);
});
