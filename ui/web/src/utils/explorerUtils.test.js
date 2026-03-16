import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PLAN_TEST_INSTRUCTION_GROUP,
  PLAN_TEST_INSTRUCTION_SINGLE,
  matchesEntryFilters,
  matchesViolationFilters,
  buildTopOffendingFiles,
  pickValidProject,
  buildDimensionPlanText,
  buildDimensionPlanFromViolations,
} from './explorerUtils.js';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const dimensions = [
  {
    dimension: 'maintainability',
    violations: [
      { file: 'lib/a.sh', severity: 'critical', principle: 'Single Responsibility' },
      { file: 'lib/a.sh', severity: 'major',    principle: 'Modularity' },
      { file: 'lib/b.sh', severity: 'minor',    principle: 'Modularity' },
    ],
  },
  {
    dimension: 'performance',
    violations: [
      { file: 'lib/a.sh', severity: 'major', principle: 'Execution Speed' },
      { file: 'lib/c.sh', severity: 'major', principle: 'Execution Speed' },
    ],
  },
];

// ---------------------------------------------------------------------------
// PLAN_TEST_INSTRUCTION constants
// ---------------------------------------------------------------------------

test('PLAN_TEST_INSTRUCTION_GROUP is a non-empty string', () => {
  assert.equal(typeof PLAN_TEST_INSTRUCTION_GROUP, 'string');
  assert.ok(PLAN_TEST_INSTRUCTION_GROUP.length > 0);
});

test('PLAN_TEST_INSTRUCTION_SINGLE is a non-empty string', () => {
  assert.equal(typeof PLAN_TEST_INSTRUCTION_SINGLE, 'string');
  assert.ok(PLAN_TEST_INSTRUCTION_SINGLE.length > 0);
});

test('PLAN_TEST_INSTRUCTION_GROUP and SINGLE are different strings', () => {
  assert.notEqual(PLAN_TEST_INSTRUCTION_GROUP, PLAN_TEST_INSTRUCTION_SINGLE);
});

// ---------------------------------------------------------------------------
// matchesEntryFilters
// ---------------------------------------------------------------------------

test('matchesEntryFilters returns true when no filters are set', () => {
  const entry = { file: 'src/foo.js', principle: 'DRY' };
  assert.equal(matchesEntryFilters(entry, {}), true);
});

test('matchesEntryFilters returns true when principle is in selectedPrinciples', () => {
  const entry = { file: 'src/foo.js', principle: 'DRY' };
  assert.equal(matchesEntryFilters(entry, { selectedPrinciples: ['DRY', 'SOLID'] }), true);
});

test('matchesEntryFilters returns false when principle is not in selectedPrinciples', () => {
  const entry = { file: 'src/foo.js', principle: 'DRY' };
  assert.equal(matchesEntryFilters(entry, { selectedPrinciples: ['SOLID'] }), false);
});

test('matchesEntryFilters matches file substring case-insensitively', () => {
  const entry = { file: 'src/FooBar.js', principle: 'DRY' };
  assert.equal(matchesEntryFilters(entry, { fileFilter: 'foobar' }), true);
});

test('matchesEntryFilters returns false when file does not match fileFilter', () => {
  const entry = { file: 'src/foo.js', principle: 'DRY' };
  assert.equal(matchesEntryFilters(entry, { fileFilter: 'bar' }), false);
});

test('matchesEntryFilters trims fileFilter whitespace', () => {
  const entry = { file: 'src/foo.js', principle: 'DRY' };
  assert.equal(matchesEntryFilters(entry, { fileFilter: '  foo  ' }), true);
});

// ---------------------------------------------------------------------------
// matchesViolationFilters
// ---------------------------------------------------------------------------

test('matchesViolationFilters returns true when no filters are set', () => {
  const entry = { file: 'a.js', severity: 'major', principle: 'DRY' };
  assert.equal(matchesViolationFilters(entry, {}), true);
});

test('matchesViolationFilters returns false when severity does not match', () => {
  const entry = { file: 'a.js', severity: 'minor', principle: 'DRY' };
  assert.equal(matchesViolationFilters(entry, { selectedSeverities: ['critical'] }), false);
});

test('matchesViolationFilters returns true when severity matches', () => {
  const entry = { file: 'a.js', severity: 'major', principle: 'DRY' };
  assert.equal(matchesViolationFilters(entry, { selectedSeverities: ['major', 'critical'] }), true);
});

test('matchesViolationFilters normalizes unknown severity values', () => {
  const entry = { file: 'a.js', severity: 'weird', principle: 'DRY' };
  assert.equal(matchesViolationFilters(entry, { selectedSeverities: ['unknown'] }), true);
});

test('matchesViolationFilters delegates principle and file checks to matchesEntryFilters', () => {
  const entry = { file: 'src/foo.js', severity: 'major', principle: 'SOLID' };
  assert.equal(
    matchesViolationFilters(entry, { selectedPrinciples: ['DRY'], selectedSeverities: [] }),
    false
  );
});

// ---------------------------------------------------------------------------
// buildTopOffendingFiles
// ---------------------------------------------------------------------------

test('buildTopOffendingFiles aggregates totals and dimensions', () => {
  const result = buildTopOffendingFiles(dimensions, {
    selectedPrinciples: [],
    selectedSeverities: [],
    fileFilter: '',
  });

  assert.equal(result[0].file, 'lib/a.sh');
  assert.equal(result[0].total, 3);
  assert.equal(result[0].critical, 1);
  assert.equal(result[0].major, 2);
  assert.equal(result[0].minor, 0);
  assert.equal(result[0].dimensionsCount, 2);
});

test('buildTopOffendingFiles applies severity and principle filters', () => {
  const result = buildTopOffendingFiles(dimensions, {
    selectedPrinciples: ['Execution Speed'],
    selectedSeverities: ['major'],
    fileFilter: '',
  });

  assert.equal(result.length, 2);
  assert.equal(result[0].file, 'lib/a.sh');
  assert.equal(result[1].file, 'lib/c.sh');
});

test('buildTopOffendingFiles respects the limit parameter', () => {
  const result = buildTopOffendingFiles(dimensions, {}, 1);
  assert.equal(result.length, 1);
  assert.equal(result[0].file, 'lib/a.sh');
});

test('buildTopOffendingFiles returns empty array for empty dimensions', () => {
  const result = buildTopOffendingFiles([], {});
  assert.deepEqual(result, []);
});

test('buildTopOffendingFiles sorts by critical then major then minor', () => {
  const dims = [
    {
      dimension: 'X',
      violations: [
        { file: 'z.js', severity: 'minor', principle: 'P' },
        { file: 'a.js', severity: 'critical', principle: 'P' },
      ],
    },
  ];
  const result = buildTopOffendingFiles(dims, {});
  assert.equal(result[0].file, 'a.js');
  assert.equal(result[1].file, 'z.js');
});

test('buildTopOffendingFiles includes principlesCount on each item', () => {
  const result = buildTopOffendingFiles(dimensions, {});
  const aEntry = result.find(r => r.file === 'lib/a.sh');
  assert.ok(aEntry);
  assert.equal(typeof aEntry.principlesCount, 'number');
  assert.ok(aEntry.principlesCount >= 1);
});

test('buildTopOffendingFiles includes violationsBySeverity on each item', () => {
  const result = buildTopOffendingFiles(dimensions, {});
  const aEntry = result.find(r => r.file === 'lib/a.sh');
  assert.ok(aEntry);
  assert.ok(Array.isArray(aEntry.violationsBySeverity.critical));
  assert.ok(Array.isArray(aEntry.violationsBySeverity.major));
  assert.ok(Array.isArray(aEntry.violationsBySeverity.minor));
  assert.ok(Array.isArray(aEntry.violationsBySeverity.unknown));
});

test('buildTopOffendingFiles includes sorted dimensions array on each item', () => {
  const result = buildTopOffendingFiles(dimensions, {});
  const aEntry = result.find(r => r.file === 'lib/a.sh');
  assert.ok(Array.isArray(aEntry.dimensions));
  assert.deepEqual(aEntry.dimensions, [...aEntry.dimensions].sort((a, b) => a.localeCompare(b)));
});

// ---------------------------------------------------------------------------
// pickValidProject
// ---------------------------------------------------------------------------

test('pickValidProject keeps selected when it still exists', () => {
  const projects = [{ name: 'alpha' }, { name: 'beta' }];
  assert.equal(pickValidProject(projects, 'beta'), 'beta');
});

test('pickValidProject falls back to first when selected is invalid', () => {
  const projects = [{ name: 'alpha' }, { name: 'beta' }];
  assert.equal(pickValidProject(projects, 'missing'), 'alpha');
});

test('pickValidProject returns empty string when no projects', () => {
  assert.equal(pickValidProject([], 'anything'), '');
});

test('pickValidProject returns first project when selected is empty string', () => {
  const projects = [{ name: 'alpha' }, { name: 'beta' }];
  assert.equal(pickValidProject(projects, ''), 'alpha');
});

test('pickValidProject handles non-array input gracefully', () => {
  assert.equal(pickValidProject(null, 'alpha'), '');
  assert.equal(pickValidProject(undefined, 'alpha'), '');
});

// ---------------------------------------------------------------------------
// buildDimensionPlanText
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
