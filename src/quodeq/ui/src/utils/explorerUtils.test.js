import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PLAN_TEST_INSTRUCTION_GROUP,
  PLAN_TEST_INSTRUCTION_SINGLE,
  matchesEntryFilters,
  matchesViolationFilters,
  buildTopOffendingFiles,
  pickValidProject,
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

test('buildTopOffendingFiles preserves provenanceDowngrade on aggregated violations (#656)', () => {
  // The aggregator builds an explicit object literal; if it does not copy
  // provenanceDowngrade, the FileDetailPage "downgraded from critical" badge
  // silently never renders on the top-offending-files navigation path.
  const dims = [
    {
      dimension: 'Security',
      violations: [
        { file: 'd.py', severity: 'major', principle: 'P', provenanceDowngrade: true },
        { file: 'd.py', severity: 'major', principle: 'P', provenanceDowngrade: false },
      ],
    },
  ];
  const result = buildTopOffendingFiles(dims, {});
  const entry = result.find(r => r.file === 'd.py');
  assert.ok(entry);
  const majors = entry.violationsBySeverity.major;
  assert.equal(majors.length, 2);
  assert.equal(majors[0].provenanceDowngrade, true);
  assert.equal(majors[1].provenanceDowngrade, false);
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

