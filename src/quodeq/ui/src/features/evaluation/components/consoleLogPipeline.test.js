import test from 'node:test';
import assert from 'node:assert/strict';
import {
  cleanLine, dedupeConsecutive, buildPipeline, advancePipeline, trailerText,
} from './consoleLogPipeline.js';

const reference = (lines) => dedupeConsecutive(lines.map(cleanLine));
const texts = (state) => state.rows.map((r) => r.text);

function countingClean() {
  const box = { calls: 0 };
  box.clean = (text) => { box.calls += 1; return cleanLine(text); };
  return box;
}

test('cleanLine strips real and bare SGR codes but keeps [maintainability]', () => {
  assert.equal(cleanLine('\x1b[0;34m[INFO]\x1b[0m  hi'), '[INFO] hi');
  assert.equal(cleanLine('[0;34m[maintainability]'), '[maintainability]');
  assert.equal(cleanLine(null), '');
});

test('append cleans only the new lines and dedupes across the batch boundary', () => {
  const c = countingClean();
  const one = buildPipeline(['a', '[INFO] b'], 0, c.clean);
  assert.equal(c.calls, 2);
  const two = advancePipeline(one, ['a', '[INFO] b', 'b', 'c'], 0, c.clean);
  assert.equal(c.calls, 4);
  assert.deepEqual(texts(two), ['a', '[INFO] b', 'c']);
  assert.deepEqual(texts(two), reference(['a', '[INFO] b', 'b', 'c']));
});

test('front trim keeps surviving rows as the same objects (stable keys)', () => {
  const one = buildPipeline(['a', 'b', 'c'], 0);
  const two = advancePipeline(one, ['b', 'c', 'd'], 1);
  assert.equal(two.rows[0], one.rows[1]);
  assert.equal(two.rows[1], one.rows[2]);
  assert.deepEqual(two.rows.map((r) => r.seq), [1, 2, 3]);
});

test('front trim re-shows a first line that was suppressed as a duplicate', () => {
  const c = countingClean();
  const one = buildPipeline(['x', 'hb', 'hb', 'y'], 0, c.clean);
  const two = advancePipeline(one, ['hb', 'y', 'z'], 2, c.clean);
  assert.deepEqual(texts(two), reference(['hb', 'y', 'z']));
  assert.equal(two.rows[0].seq, 2);
  assert.equal(c.calls, 4 + 2);
});

test('identical heartbeat lines at the cap match a full recompute', () => {
  const one = buildPipeline(['hb', 'hb', 'hb'], 0);
  const two = advancePipeline(one, ['hb', 'hb', 'hb'], 1);
  assert.deepEqual(texts(two), ['hb']);
  assert.equal(two.endSeq, 4);
});

test('a reset (firstSeq jumps to the old endSeq) drops every old row', () => {
  const one = buildPipeline(['a', 'b'], 0);
  const empty = advancePipeline(one, [], 2);
  assert.deepEqual(empty.rows, []);
  const next = advancePipeline(empty, ['a'], 2);
  assert.deepEqual(texts(next), ['a']);
});

test('no firstSeq, or a firstSeq that went backwards, falls back to a full build', () => {
  const one = buildPipeline(['a', 'b'], 5);
  assert.deepEqual(texts(advancePipeline(one, ['q'], undefined)), ['q']);
  assert.deepEqual(texts(advancePipeline(one, ['q', 'r'], 1)), ['q', 'r']);
  assert.deepEqual(texts(advancePipeline(null, null, undefined)), []);
});

test('unchanged input returns the previous state object', () => {
  const lines = ['a', 'b'];
  const one = buildPipeline(lines, 0);
  assert.equal(advancePipeline(one, lines.slice(), 0), one);
});

test('trailerText hides a trailer that dedupes against the last row', () => {
  const state = buildPipeline(['evaluation cancelled'], 0);
  assert.equal(trailerText(state, '[INFO] evaluation cancelled'), null);
  assert.equal(trailerText(state, 'done'), 'done');
  assert.equal(trailerText(state, null), null);
});

// Deterministic LCG so a failure reproduces.
function rng(seed) {
  let s = seed;
  return () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
}

test('randomized: incremental result equals a full recompute after every batch', () => {
  const alphabet = ['hb', 'hb', '[INFO] hb', 'a', '', '  [rel] 1m2s | 1 active', '  [rel] 1m9s | 1 active', 'b'];
  const cap = 7;
  const rand = rng(42);
  let buf = { lines: [], firstSeq: 0 };
  let state = null;
  for (let step = 0; step < 400; step += 1) {
    if (rand() < 0.05) {
      buf = { lines: [], firstSeq: buf.firstSeq + buf.lines.length };
    } else {
      const n = 1 + Math.floor(rand() * 4);
      const batch = Array.from({ length: n }, () => alphabet[Math.floor(rand() * alphabet.length)]);
      const merged = buf.lines.concat(batch);
      const drop = Math.max(0, merged.length - cap);
      buf = { lines: merged.slice(drop), firstSeq: buf.firstSeq + drop };
    }
    state = advancePipeline(state, buf.lines, buf.firstSeq);
    assert.deepEqual(texts(state), reference(buf.lines), `step ${step}`);
    const seqs = state.rows.map((r) => r.seq);
    assert.ok(seqs.every((s, i) => i === 0 || s > seqs[i - 1]), `seqs increase at step ${step}`);
    assert.ok(seqs.every((s) => s >= buf.firstSeq && s < buf.firstSeq + buf.lines.length));
  }
});
