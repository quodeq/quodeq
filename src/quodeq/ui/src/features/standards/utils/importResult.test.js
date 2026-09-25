import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyImportResult, parseImportFile, IMPORT_OUTCOME, PARSE_FILE_ERROR, MAX_FILE_SIZE } from './importResult.js';

// classifyImportResult: characterizes the three outcomes ImportModal's old
// inline importEvaluator() branched on.

test('classifyImportResult: a _conflict result classifies as CONFLICT with existing + warnings', () => {
  const result = { _conflict: true, existing: { id: 'x', name: 'Existing' }, warnings: ['w1'] };
  const out = classifyImportResult(result, false);
  assert.deepEqual(out, { kind: IMPORT_OUTCOME.CONFLICT, conflict: { id: 'x', name: 'Existing' }, warnings: ['w1'] });
});

test('classifyImportResult: CONFLICT defaults warnings to [] when absent', () => {
  const result = { _conflict: true, existing: { id: 'x' } };
  const out = classifyImportResult(result, false);
  assert.deepEqual(out.warnings, []);
});

test('classifyImportResult: warnings without force classifies as WARNINGS', () => {
  const result = { warnings: ['careful'] };
  const out = classifyImportResult(result, false);
  assert.deepEqual(out, { kind: IMPORT_OUTCOME.WARNINGS, warnings: ['careful'] });
});

test('classifyImportResult: warnings WITH force classifies as SUCCESS (force skips the warnings gate)', () => {
  const result = { warnings: ['careful'], detail: { id: 'stored-id' } };
  const out = classifyImportResult(result, true);
  assert.deepEqual(out, { kind: IMPORT_OUTCOME.SUCCESS, id: 'stored-id' });
});

test('classifyImportResult: no conflict, no warnings classifies as SUCCESS with detail.id', () => {
  const result = { detail: { id: 'stored-id' } };
  const out = classifyImportResult(result, false);
  assert.deepEqual(out, { kind: IMPORT_OUTCOME.SUCCESS, id: 'stored-id' });
});

test('classifyImportResult: SUCCESS with no detail.id leaves id undefined (caller falls back to the file id)', () => {
  const out = classifyImportResult({}, false);
  assert.deepEqual(out, { kind: IMPORT_OUTCOME.SUCCESS, id: undefined });
});

// parseImportFile: characterizes handleFileInput's old size/parse/shape checks.

function fakeFile({ size, text }) {
  return { size, text: async () => text };
}

test('parseImportFile: oversized file returns TOO_LARGE with the file size', async () => {
  const file = fakeFile({ size: MAX_FILE_SIZE + 1, text: '{}' });
  const out = await parseImportFile(file);
  assert.deepEqual(out, { ok: false, error: PARSE_FILE_ERROR.TOO_LARGE, size: MAX_FILE_SIZE + 1 });
});

test('parseImportFile: unparsable JSON returns INVALID_JSON with the cause', async () => {
  const file = fakeFile({ size: 10, text: 'not json' });
  const out = await parseImportFile(file);
  assert.equal(out.ok, false);
  assert.equal(out.error, PARSE_FILE_ERROR.INVALID_JSON);
  assert.ok(out.cause instanceof Error);
});

test('parseImportFile: a JSON array parses but fails the object-shape check', async () => {
  const file = fakeFile({ size: 10, text: '[1,2,3]' });
  const out = await parseImportFile(file);
  assert.deepEqual(out, { ok: false, error: PARSE_FILE_ERROR.INVALID_JSON_OBJECT });
});

test('parseImportFile: a JSON primitive fails the object-shape check', async () => {
  const file = fakeFile({ size: 10, text: '"just a string"' });
  const out = await parseImportFile(file);
  assert.deepEqual(out, { ok: false, error: PARSE_FILE_ERROR.INVALID_JSON_OBJECT });
});

test('parseImportFile: a valid JSON object parses successfully', async () => {
  const file = fakeFile({ size: 10, text: '{"id":"my-standard"}' });
  const out = await parseImportFile(file);
  assert.deepEqual(out, { ok: true, data: { id: 'my-standard' } });
});
