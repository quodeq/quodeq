// The naming ratchet is one custom rule plus an empty baseline. Pin both
// directions (what it flags, what stays quiet) so a regex that quietly stops
// matching cannot leave the gate green, and pin the baseline at zero.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { ESLint } from 'eslint';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const UI_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const eslint = new ESLint({ cwd: UI_ROOT, overrideConfigFile: 'eslint.naming.config.js', allowInlineConfig: false });

async function names(code, file = 'src/probe.js') {
  const [result] = await eslint.lintText(code, { filePath: join(UI_ROOT, file) });
  assert.equal(result.messages.filter((m) => m.fatal).length, 0, 'probe must parse');
  return result.messages.filter((m) => m.ruleId === 'naming/module-names').map((m) => m.message.match(/'([^']+)'/)[1]);
}

test('a module constant holding a literal or frozen object must be UPPER_SNAKE', async () => {
  assert.deepEqual(await names('export const maxRows = 5;'), ['maxRows']);
  assert.deepEqual(await names("const Label = 'x';"), ['Label']);
  assert.deepEqual(await names("export const runState = Object.freeze({ DONE: 'done' });"), ['runState']);
  assert.deepEqual(await names('const offset = -1;'), ['offset']);
});

test('UPPER_SNAKE constants, computed values and locals are quiet', async () => {
  assert.deepEqual(await names('export const MAX_ROWS = 5;'), []);
  assert.deepEqual(await names('const _LIMIT = 3;'), []);
  assert.deepEqual(await names("export const RUN_STATE = Object.freeze({ DONE: 'done' });"), []);
  assert.deepEqual(await names('export const rows = [1, 2];'), []);
  assert.deepEqual(await names('export const total = a + b;'), []);
  assert.deepEqual(await names('export function f() { const local = 5; return local; }'), []);
});

test('a module function must be camelCase', async () => {
  assert.deepEqual(await names('export function Build_rows() {}'), ['Build_rows']);
  assert.deepEqual(await names('function BuildRows() {}'), ['BuildRows']);
  assert.deepEqual(await names('export default function Page() {}'), ['Page']);
});

test('camelCase functions, _private helpers and .jsx components are quiet', async () => {
  assert.deepEqual(await names('export function buildRows() {}'), []);
  assert.deepEqual(await names('function _buildRows() {}'), []);
  assert.deepEqual(await names('export default function Page() { return null; }', 'src/Page.jsx'), []);
  assert.deepEqual(await names('export const SSE_ENABLED = () => true;'), []);
});

test('test and fixture files are out of scope', async () => {
  assert.deepEqual(await names('const lower = 1;', 'src/probe.test.js'), []);
  assert.deepEqual(await names('const lower = 1;', 'src/probe.fixtures.js'), []);
});

test('the naming baseline stays empty and its ceiling at zero', () => {
  assert.deepEqual(JSON.parse(readFileSync(join(UI_ROOT, 'tools/naming_baseline.json'), 'utf8')), {});
  assert.match(readFileSync(join(UI_ROOT, 'tools/check_naming.mjs'), 'utf8'), /const TOTAL_CEILING = 0;/);
});
