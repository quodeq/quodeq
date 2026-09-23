// The vocabulary-literal gate is a list of no-restricted-syntax selectors.
// A selector that quietly stops matching leaves the ratchet green while bare
// literals creep back, so pin both directions: what must be flagged, and what
// must stay quiet.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ESLint } from 'eslint';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const UI_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const eslint = new ESLint({ cwd: UI_ROOT, overrideConfigFile: 'eslint.vocab.config.js', allowInlineConfig: false });

async function count(code) {
  const [result] = await eslint.lintText(code, { filePath: join(UI_ROOT, 'src/probe.js') });
  assert.equal(result.messages.filter((m) => m.fatal).length, 0, 'probe must parse');
  return result.messages.filter((m) => m.ruleId === 'no-restricted-syntax').length;
}

test('an array of two or more words from one vocabulary is flagged', async () => {
  assert.ok(await count("export const T = ['done', 'failed'];") > 0);
  assert.ok(await count("export const S = ['critical', 'major', 'minor'];") > 0);
  assert.ok(await count("export const G = Object.freeze(['Poor', 'Good']);") > 0);
});

test('an array with at most one word per vocabulary is quiet', async () => {
  assert.equal(await count("export const A = ['done', 'utf-8'];"), 0);
  assert.equal(await count("export const B = ['critical', 'Poor'];"), 0);
});

test('a vocabulary fallback of a vocabulary-named read is flagged', async () => {
  assert.equal(await count("export const f = (row) => row.status ?? 'running';"), 1);
  assert.equal(await count("export const f = (state) => state || 'done';"), 1);
  assert.equal(await count("export const f = (row) => row.label ?? 'done';"), 0);
});

test('the left operand of `in` is a key test, not a state comparison', async () => {
  assert.equal(await count("export const f = (payload) => 'error' in payload;"), 0);
  assert.equal(await count("export const f = (s) => s === 'error';"), 1);
});

test('finding-type words are gated like the other vocabularies', async () => {
  assert.equal(await count("export const f = (item) => item.kind === 'violation';"), 1);
  assert.equal(await count("export const f = (filter) => filter !== 'compliance';"), 1);
  assert.equal(await count("export const f = (bucket) => bucket === 'violations';"), 0);
});
