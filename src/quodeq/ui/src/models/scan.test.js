import test from 'node:test';
import assert from 'node:assert/strict';
import { createScanSummary } from './scan.js';

test('createScanSummary maps a snake_case raw payload to camelCase', () => {
  const s = createScanSummary({
    total_files: 120,
    code_files: 80,
    untracked_files: 3,
    languages: { py: 60, js: 20 },
    branches: ['main', 'dev'],
    modules: ['pkg'],
    scanned_at: '2026-09-25T00:00:00Z',
  });
  assert.deepEqual(s, {
    totalFiles: 120,
    codeFiles: 80,
    untrackedFiles: 3,
    languages: { py: 60, js: 20 },
    branches: ['main', 'dev'],
    modules: ['pkg'],
    scannedAt: '2026-09-25T00:00:00Z',
  });
});

test('createScanSummary defaults missing fields', () => {
  const s = createScanSummary({});
  assert.deepEqual(s, {
    totalFiles: 0,
    codeFiles: 0,
    untrackedFiles: 0,
    languages: {},
    branches: [],
    modules: [],
    scannedAt: '',
  });
});

test('createScanSummary passes through a non-object unchanged', () => {
  assert.equal(createScanSummary(null), null);
  assert.equal(createScanSummary(undefined), undefined);
});
