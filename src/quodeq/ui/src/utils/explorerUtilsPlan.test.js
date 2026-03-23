import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PLAN_TEST_INSTRUCTION_GROUP,
  buildDimensionPlanText,
  buildDimensionPlanFromViolations,
} from './explorerUtils.js';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const evalDataFull = {
  dimension: 'Maintainability',
  principles: [
    {
      name: 'DRY',
      findings: 'Duplicate logic across modules.',
      violations: [
        { severity: 'critical', file: 'src/a.js', snippet: 'const x = 1;\nconst y = 1;' },
      ],
    },
    {
      name: 'SOLID',
      findings: 'Classes do too much.',
      violations: [
        { severity: 'major', file: 'src/b.js', snippet: 'class God { ... }' },
      ],
    },
    {
      name: 'Clean',
      findings: null,
      violations: [],
    },
  ],
};

// ---------------------------------------------------------------------------
// buildDimensionPlanText
// ---------------------------------------------------------------------------

test('buildDimensionPlanText produces markdown fix plan from evalData', () => {
  const result = buildDimensionPlanText(evalDataFull);

  assert.ok(result.includes('# Fix Plan: Maintainability dimension'), 'has dimension title');
  assert.ok(result.includes('**Total violations:** 2'), 'has total count');
  assert.ok(result.includes('## Critical violations (1)'), 'has critical section');
  assert.ok(result.includes('## Major violations (1)'), 'has major section');
  assert.ok(result.includes('### 1. DRY'), 'has DRY principle');
  assert.ok(result.includes('src/a.js'), 'has file ref');
  assert.ok(result.includes('Duplicate logic across modules.'), 'has findings as why');
  assert.ok(result.includes('const x = 1;'), 'has code snippet');
  assert.ok(result.includes('### 1. SOLID'), 'has SOLID principle');
  assert.ok(!result.includes('## Minor violations'), 'no empty minor section');
  assert.ok(result.includes('For each violation above'), 'has closing instruction');
});

test('buildDimensionPlanText returns empty string when no violations', () => {
  const evalData = {
    dimension: 'Reliability',
    principles: [
      { name: 'ErrorHandling', findings: null, violations: [] },
    ],
  };

  const result = buildDimensionPlanText(evalData);
  assert.equal(result, '');
});

test('buildDimensionPlanText includes PLAN_TEST_INSTRUCTION_GROUP at end', () => {
  const result = buildDimensionPlanText(evalDataFull);
  assert.ok(result.includes(PLAN_TEST_INSTRUCTION_GROUP));
});

test('buildDimensionPlanText uses fallback dimension name when missing', () => {
  const evalData = {
    principles: [
      {
        name: 'DRY',
        findings: null,
        violations: [{ severity: 'minor', file: 'x.js' }],
      },
    ],
  };
  const result = buildDimensionPlanText(evalData);
  assert.ok(result.includes('# Fix Plan:'));
});

// ---------------------------------------------------------------------------
// buildDimensionPlanFromViolations
// ---------------------------------------------------------------------------

const sampleViolations = [
  { severity: 'critical', file: 'lib/x.js', line: 10, principle: 'DRY', reason: 'Duplicate code.', snippet: 'const a = 1;' },
  { severity: 'major',    file: 'lib/y.js', line: 20, principle: 'SOLID', reason: 'Too many responsibilities.', snippet: 'class Big {}' },
  { severity: 'minor',    file: 'lib/z.js',            principle: 'Clean', reason: null, snippet: null },
];

test('buildDimensionPlanFromViolations returns empty string for empty list', () => {
  assert.equal(buildDimensionPlanFromViolations('X', []), '');
  assert.equal(buildDimensionPlanFromViolations('X', null), '');
});

test('buildDimensionPlanFromViolations includes dimension name in header', () => {
  const result = buildDimensionPlanFromViolations('Performance', sampleViolations);
  assert.ok(result.includes('# Fix Plan: Performance dimension'));
});

test('buildDimensionPlanFromViolations includes total violation count', () => {
  const result = buildDimensionPlanFromViolations('Performance', sampleViolations);
  assert.ok(result.includes(`**Total violations:** ${sampleViolations.length}`));
});

test('buildDimensionPlanFromViolations groups by severity in order', () => {
  const result = buildDimensionPlanFromViolations('Performance', sampleViolations);
  const critIdx = result.indexOf('## Critical violations');
  const majIdx  = result.indexOf('## Major violations');
  const minIdx  = result.indexOf('## Minor violations');
  assert.ok(critIdx < majIdx, 'critical before major');
  assert.ok(majIdx < minIdx, 'major before minor');
});

test('buildDimensionPlanFromViolations includes principle name as violation heading', () => {
  const result = buildDimensionPlanFromViolations('Performance', sampleViolations);
  assert.ok(result.includes('DRY'));
  assert.ok(result.includes('SOLID'));
});

test('buildDimensionPlanFromViolations includes reason when present', () => {
  const result = buildDimensionPlanFromViolations('Performance', sampleViolations);
  assert.ok(result.includes('Duplicate code.'));
  assert.ok(result.includes('Too many responsibilities.'));
});

test('buildDimensionPlanFromViolations includes snippet when present', () => {
  const result = buildDimensionPlanFromViolations('Performance', sampleViolations);
  assert.ok(result.includes('const a = 1;'));
  assert.ok(result.includes('class Big {}'));
});

test('buildDimensionPlanFromViolations includes file and line reference', () => {
  const result = buildDimensionPlanFromViolations('Performance', sampleViolations);
  assert.ok(result.includes('lib/x.js:10'));
});

test('buildDimensionPlanFromViolations includes PLAN_TEST_INSTRUCTION_GROUP at end', () => {
  const result = buildDimensionPlanFromViolations('Performance', sampleViolations);
  assert.ok(result.endsWith(PLAN_TEST_INSTRUCTION_GROUP));
});
