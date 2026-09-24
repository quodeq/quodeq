import test from 'node:test';
import assert from 'node:assert/strict';
import { EMPTY_LOG_BUFFER, appendLines, clearLines } from './logBuffer.js';

test('appendLines: appends under the cap without moving firstSeq', () => {
  const next = appendLines(EMPTY_LOG_BUFFER, ['a', 'b'], 5);
  assert.deepEqual(next, { lines: ['a', 'b'], firstSeq: 0 });
});

test('appendLines: a front trim advances firstSeq by the dropped count', () => {
  const one = appendLines(EMPTY_LOG_BUFFER, ['a', 'b', 'c'], 4);
  const two = appendLines(one, ['d', 'e', 'f'], 4);
  assert.deepEqual(two, { lines: ['c', 'd', 'e', 'f'], firstSeq: 2 });
});

test('appendLines: identical lines still count one by one', () => {
  const one = appendLines(EMPTY_LOG_BUFFER, ['hb', 'hb', 'hb'], 3);
  const two = appendLines(one, ['hb'], 3);
  assert.deepEqual(two, { lines: ['hb', 'hb', 'hb'], firstSeq: 1 });
});

test('appendLines: an empty batch returns prev itself', () => {
  const one = appendLines(EMPTY_LOG_BUFFER, ['a'], 3);
  assert.equal(appendLines(one, [], 3), one);
});

test('appendLines: never mutates prev or the batch', () => {
  const batch = ['a', 'b'];
  const one = appendLines(EMPTY_LOG_BUFFER, batch, 3);
  appendLines(one, ['c', 'd'], 3);
  assert.deepEqual(one.lines, ['a', 'b']);
  assert.deepEqual(batch, ['a', 'b']);
  assert.deepEqual(EMPTY_LOG_BUFFER.lines, []);
});

test('clearLines: a reset moves firstSeq past every old line', () => {
  const one = appendLines(EMPTY_LOG_BUFFER, ['a', 'b', 'c'], 2);
  assert.deepEqual(clearLines(one), { lines: [], firstSeq: 3 });
});

test('clearLines: clearing an empty buffer returns it unchanged', () => {
  assert.equal(clearLines(EMPTY_LOG_BUFFER), EMPTY_LOG_BUFFER);
});
