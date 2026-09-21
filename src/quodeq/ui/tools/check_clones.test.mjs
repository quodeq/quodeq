// Unit tests for tools/check_clones.mjs: the jscpd clone ratchet.
//
// `evaluateGate` and `parseReport` are pure (no jscpd subprocess, no fixed
// baseline path), so these drive them with a fixture report and a tmp
// baseline file instead of shelling out to jscpd.
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { describe, evaluateGate, loadBaseline, parseReport } from './check_clones.mjs';

function payload(...pairs) {
  return {
    duplicates: pairs.map(([nameA, startA, endA, nameB, startB, endB]) => ({
      format: 'python',
      lines: endA - startA + 1,
      firstFile: { name: nameA, start: startA, end: endA },
      secondFile: { name: nameB, start: startB, end: endB },
    })),
  };
}

function withTmpDir(fn) {
  const dir = mkdtempSync(path.join(tmpdir(), 'check-clones-test-'));
  try {
    return fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test('parseReport keys are repo-relative and pair-sorted', () => {
  const clones = parseReport(payload(['../a.py', 1, 5, '../b.py', 9, 13]), '/repo/ui', '/repo');
  assert.deepEqual(clones.map((c) => c.key), ['a.py:1-5|b.py:9-13']);
});

test('parseReport key is pair-order independent', () => {
  const forward = parseReport(payload(['../a.py', 1, 5, '../b.py', 9, 13]), '/repo/ui', '/repo');
  const reversed = parseReport(payload(['../b.py', 9, 13, '../a.py', 1, 5]), '/repo/ui', '/repo');
  assert.deepEqual(forward.map((c) => c.key), reversed.map((c) => c.key));
});

test('describe names the format and size', () => {
  const [clone] = parseReport(payload(['../a.py', 10, 17, '../b.py', 1, 8]), '/repo/ui', '/repo');
  const line = describe(clone);
  assert.match(line, /a\.py:10-17/);
  assert.match(line, /8 lines/);
  assert.match(line, /python/);
});

test('a clone outside the baseline is flagged as new', () => {
  withTmpDir((dir) => {
    const baselinePath = path.join(dir, 'clones_baseline.json');
    writeFileSync(baselinePath, '[]\n', 'utf8');
    const [clone] = parseReport(payload(['../a.py', 1, 5, '../b.py', 1, 5]), '/repo/ui', '/repo');

    const { code, lines } = evaluateGate([clone], baselinePath, { ceiling: 10 });

    assert.equal(code, 1);
    assert.ok(lines.some((l) => l.includes('a.py:1-5|b.py:1-5')));
  });
});

test('a clone already in the baseline passes the gate', () => {
  withTmpDir((dir) => {
    const baselinePath = path.join(dir, 'clones_baseline.json');
    writeFileSync(baselinePath, JSON.stringify(['a.py:1-5|b.py:1-5']), 'utf8');
    const [clone] = parseReport(payload(['../a.py', 1, 5, '../b.py', 1, 5]), '/repo/ui', '/repo');

    const { code, lines } = evaluateGate([clone], baselinePath, { ceiling: 10 });

    assert.equal(code, 0);
    assert.ok(lines.some((l) => l.includes('OK')));
  });
});

test('a baseline grown past the ceiling fails even with no new clones', () => {
  withTmpDir((dir) => {
    const baselinePath = path.join(dir, 'clones_baseline.json');
    writeFileSync(baselinePath, JSON.stringify(['a.py:1-5|b.py:1-5']), 'utf8');
    const [clone] = parseReport(payload(['../a.py', 1, 5, '../b.py', 1, 5]), '/repo/ui', '/repo');

    const { code, lines } = evaluateGate([clone], baselinePath, { ceiling: 0 });

    assert.equal(code, 1);
    assert.ok(lines.some((l) => l.includes('ceiling 0')));
  });
});

test('--update writes the baseline and the gate then passes', () => {
  withTmpDir((dir) => {
    const baselinePath = path.join(dir, 'clones_baseline.json');
    const [clone] = parseReport(payload(['../a.py', 1, 5, '../b.py', 1, 5]), '/repo/ui', '/repo');

    const written = evaluateGate([clone], baselinePath, { update: true, ceiling: 10 });
    assert.equal(written.code, 0);
    assert.deepEqual(loadBaseline(baselinePath), new Set(['a.py:1-5|b.py:1-5']));
    assert.deepEqual(JSON.parse(readFileSync(baselinePath, 'utf8')), ['a.py:1-5|b.py:1-5']);

    const { code } = evaluateGate([clone], baselinePath, { ceiling: 10 });
    assert.equal(code, 0);
  });
});

test('updating with no clones writes an empty array', () => {
  withTmpDir((dir) => {
    const baselinePath = path.join(dir, 'clones_baseline.json');
    const { code } = evaluateGate([], baselinePath, { update: true });
    assert.equal(code, 0);
    assert.deepEqual(JSON.parse(readFileSync(baselinePath, 'utf8')), []);
  });
});
