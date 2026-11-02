import test from 'node:test';
import assert from 'node:assert/strict';
import { isWithheldSnippet, shownSnippet } from './withheldSnippet.js';

const TOKEN = `quodeq:snippet-withheld:${'a'.repeat(64)}`;

test('a withheld token is never shown as code', () => {
  assert.equal(isWithheldSnippet(TOKEN), true);
  assert.equal(shownSnippet(TOKEN), '');
});

test('real code and blanks pass through', () => {
  assert.equal(isWithheldSnippet('x = 1'), false);
  assert.equal(shownSnippet('x = 1'), 'x = 1');
  assert.equal(shownSnippet(null), '');
});
