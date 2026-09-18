import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRadialPrinciples, buildEnrichedPrinciples } from './explorerPrincipleView.js';

test('buildRadialPrinciples: flags insufficient-evidence grades and keeps a real score otherwise', () => {
  const grades = [
    { principle: 'A', grade: 'Insufficient', score: 90 },
    { principle: 'B', grade: 'A', score: 85 },
  ];
  const points = buildRadialPrinciples(grades);
  assert.deepEqual(points[0], { name: 'A', score: null, hasEvidence: false });
  assert.deepEqual(points[1], { name: 'B', score: 85, hasEvidence: true });
});

test('buildEnrichedPrinciples: groups violations by principle and counts them per principle grade', () => {
  const grades = [{ principle: 'A' }, { principle: 'B' }];
  const violations = [
    { principle: 'A', severity: 'major' },
    { principle: 'A', severity: 'minor' },
    { principle: 'B', severity: 'critical' },
  ];
  const enriched = buildEnrichedPrinciples(grades, violations, new Map());
  assert.equal(enriched[0].violationCount, 2);
  assert.equal(enriched[1].violationCount, 1);
});

test('buildEnrichedPrinciples: a second violation for an already-seen principle lands in the same bucket (not a fresh one)', () => {
  const grades = [{ principle: 'A' }];
  const violations = [
    { principle: 'A', file: 'first.py', severity: 'major' },
    { principle: 'A', file: 'second.py', severity: 'minor' },
  ];
  const enriched = buildEnrichedPrinciples(grades, violations, new Map());
  assert.equal(enriched[0].violationCount, 2);
  assert.equal(enriched[0].severity.major, 1);
  assert.equal(enriched[0].severity.minor, 1);
});

test('buildEnrichedPrinciples: does not throw for inputs with no violations/compliance', () => {
  assert.doesNotThrow(() => buildEnrichedPrinciples([{ principle: 'A' }], [], null));
  const enriched = buildEnrichedPrinciples([{ principle: 'A' }], [], null);
  assert.equal(enriched[0].violationCount, 0);
  assert.equal(enriched[0].complianceCount, 0);
});
