import test from 'node:test';
import assert from 'node:assert/strict';
import { formatPrincipleTable } from './shared.js';

test('formatPrincipleTable: a genuine score of 0 renders as 0, not the em-dash placeholder', () => {
  const md = formatPrincipleTable([{ principle: 'P1', score: 0, grade: 'F' }]);
  assert.match(md, /\| P1 \| 0 \| F \|/);
});

test('formatPrincipleTable: a missing score renders the em-dash placeholder', () => {
  const md = formatPrincipleTable([{ principle: 'P1', score: null, grade: null }]);
  assert.match(md, /\| P1 \| — \| — \|/);
});
