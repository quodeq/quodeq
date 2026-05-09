import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRunReport, buildFileReport, buildOverviewReport, buildDimensionReport, buildPrincipleReport } from './reportBuilder.js';

const dimensions = [
  {
    dimension: 'maintainability',
    overallScore: '7.5/10',
    overallGrade: 'B',
    violations: [
      { file: 'lib/a.sh', severity: 'critical', principle: 'SRP', title: 'Too many responsibilities' },
      { file: 'lib/b.sh', severity: 'major', principle: 'Modularity', title: 'God object' },
    ],
    compliance: [{ principle: 'SRP' }],
  },
  {
    dimension: 'performance',
    overallScore: '8.0/10',
    overallGrade: 'B',
    violations: [
      { file: 'lib/a.sh', severity: 'minor', principle: 'Speed', title: 'Slow loop' },
    ],
    compliance: [],
  },
];

const runSummary = {
  numericAverage: '7.8',
  overallGrade: 'B',
  totalViolations: 3,
  totalCompliance: 1,
  dimensionCount: 2,
  severity: { critical: 1, major: 1, minor: 1 },
};

test('buildRunReport includes title with project name and run header', () => {
  const dashboard = { dimensions, selectedRun: { runId: 'abc12345', dateLabel: '21 Apr 2025' } };
  const md = buildRunReport({ dashboard, runSummary, projectName: 'MyApp' });
  assert.match(md, /^# MyApp run report/);
  assert.match(md, /\*\*Date:\*\* 21 Apr 2025/);
  assert.match(md, /\*\*Run:\*\* abc12345/);
  assert.match(md, /\*\*Overall Score:\*\* 7\.8\/10 B/);
});

test('buildRunReport includes dimensions table and crit/major section', () => {
  const dashboard = { dimensions, selectedRun: {} };
  const md = buildRunReport({ dashboard, runSummary, projectName: 'X' });
  assert.match(md, /## Dimensions/);
  assert.match(md, /\| Maintainability \|/);
  assert.match(md, /## Top Offending Files/);
  assert.match(md, /## Critical & Major Violations \(2\)/);
  assert.match(md, /Too many responsibilities/);
});

test('buildRunReport handles empty dashboard gracefully', () => {
  const dashboard = { dimensions: [], selectedRun: {} };
  const md = buildRunReport({ dashboard, runSummary: { totalViolations: 0, totalCompliance: 0 }, projectName: 'X' });
  assert.match(md, /^# X run report/);
  assert.match(md, /No critical or major violations found\./);
});

test('buildFileReport includes file path and totals', () => {
  const file = {
    file: 'src/foo/bar.js',
    total: 3,
    critical: 1,
    major: 1,
    minor: 1,
    dimensionsCount: 2,
    compliance: [{ principle: 'Naming' }],
    violationsBySeverity: {
      critical: [{ severity: 'critical', principle: 'SRP', title: 'Bad', file: 'src/foo/bar.js', line: 12 }],
      major: [{ severity: 'major', principle: 'DRY', title: 'Repeat', file: 'src/foo/bar.js' }],
      minor: [{ severity: 'minor', principle: 'Style', title: 'Format', file: 'src/foo/bar.js' }],
    },
  };
  const md = buildFileReport(file);
  assert.match(md, /^# File report/);
  assert.match(md, /\*\*File:\*\* `src\/foo\/bar\.js`/);
  assert.match(md, /## Summary/);
  assert.match(md, /\*\*3\*\* total violations \(1 critical, 1 major, 1 minor\)/);
  assert.match(md, /\*\*1\*\* compliance findings/);
  assert.match(md, /## Violations \(3\)/);
  assert.match(md, /### Critical \(1\)/);
  assert.match(md, /## Compliance Summary \(1\)/);
});

test('buildFileReport with no violations shows "No violations found"', () => {
  const file = { file: 'empty.js', total: 0, compliance: [], violationsBySeverity: {}, dimensionsCount: 1 };
  const md = buildFileReport(file);
  assert.match(md, /No violations found\./);
});

const fileFixture = {
  file: 'src/foo/bar.js',
  total: 3,
  critical: 1,
  major: 1,
  minor: 1,
  dimensionsCount: 2,
  compliance: [{ principle: 'Naming', file: 'src/foo/bar.js' }],
  violationsBySeverity: {
    critical: [{ severity: 'critical', principle: 'SRP', title: 'Crit-1', file: 'src/foo/bar.js', line: 12 }],
    major:    [{ severity: 'major',    principle: 'DRY', title: 'Maj-1', file: 'src/foo/bar.js' }],
    minor:    [{ severity: 'minor',    principle: 'Style', title: 'Min-1', file: 'src/foo/bar.js' }],
  },
};

test('buildFileReport with no severityFilter renders all severities and compliance', () => {
  const md = buildFileReport(fileFixture);
  assert.match(md, /Crit-1/);
  assert.match(md, /Maj-1/);
  assert.match(md, /Min-1/);
  assert.match(md, /## Compliance Summary/);
});

test("buildFileReport with severityFilter='critical' shows only critical and omits compliance", () => {
  const md = buildFileReport(fileFixture, 'critical');
  assert.match(md, /Crit-1/);
  assert.doesNotMatch(md, /Maj-1/);
  assert.doesNotMatch(md, /Min-1/);
  assert.doesNotMatch(md, /## Compliance Summary/);
  assert.match(md, /## Violations \(1\)/);
});

test("buildFileReport with severityFilter='major' shows only major and omits compliance", () => {
  const md = buildFileReport(fileFixture, 'major');
  assert.doesNotMatch(md, /Crit-1/);
  assert.match(md, /Maj-1/);
  assert.doesNotMatch(md, /Min-1/);
  assert.doesNotMatch(md, /## Compliance Summary/);
  assert.match(md, /## Violations \(1\)/);
});

test("buildFileReport with severityFilter='compliance' omits violations and shows compliance", () => {
  const md = buildFileReport(fileFixture, 'compliance');
  assert.match(md, /## Violations \(0\)/);
  assert.match(md, /No violations found\./);
  assert.match(md, /## Compliance Summary \(1\)/);
});

test("buildFileReport with severityFilter='all' is identical to no filter", () => {
  const filtered = buildFileReport(fileFixture, 'all');
  const unfiltered = buildFileReport(fileFixture);
  assert.equal(filtered, unfiltered);
});

test('buildPrincipleReport includes principle, score, findings, and violations', () => {
  const md = buildPrincipleReport({
    principle: 'Single Responsibility',
    dimension: 'maintainability',
    score: '6/10',
    grade: 'C',
    violations: [
      { severity: 'critical', principle: 'Single Responsibility', title: 'Mega class', file: 'src/big.js', line: 10 },
    ],
    compliance: [{ principle: 'Single Responsibility', file: 'src/small.js', reason: 'small and focused' }],
    principleData: { findings: 'Code lacks separation.', justification: 'Several god objects.' },
    runId: 'abc12345',
    dateLabel: '21 Apr 2025',
  });
  assert.match(md, /^# Single Responsibility report/);
  assert.match(md, /\*\*Date:\*\* 21 Apr 2025/);
  assert.match(md, /\*\*Run:\*\* abc12345/);
  assert.match(md, /\*\*Dimension:\*\* maintainability/);
  assert.match(md, /\*\*Score:\*\* 6\/10 C/);
  assert.match(md, /## Findings/);
  assert.match(md, /Code lacks separation\./);
  assert.match(md, /## Justification/);
  assert.match(md, /## Violations \(1\)/);
  assert.match(md, /### Critical \(1\)/);
  assert.match(md, /## Compliance Summary \(1\)/);
});

test('buildPrincipleReport with no violations shows "No violations found"', () => {
  const md = buildPrincipleReport({ principle: 'X', violations: [], compliance: [], principleData: null });
  assert.match(md, /No violations found\./);
});

const principleFixture = {
  principle: 'SRP',
  dimension: 'maintainability',
  score: '7.5/10',
  grade: 'B',
  violations: [
    { severity: 'critical', principle: 'SRP', title: 'P-Crit', reason: 'reason-c', file: 'a.js' },
    { severity: 'major',    principle: 'SRP', title: 'P-Maj',  reason: 'reason-m', file: 'b.js' },
    { severity: 'minor',    principle: 'SRP', title: 'P-Min',  reason: 'reason-n', file: 'c.js' },
  ],
  compliance: [{ principle: 'SRP', file: 'd.js', reason: 'ok' }],
};

test('buildPrincipleReport with no severityFilter renders all severities and compliance', () => {
  const md = buildPrincipleReport(principleFixture);
  assert.match(md, /P-Crit/);
  assert.match(md, /P-Maj/);
  assert.match(md, /P-Min/);
  assert.match(md, /## Compliance Summary/);
});

test("buildPrincipleReport with severityFilter='critical' shows only critical, no compliance", () => {
  const md = buildPrincipleReport({ ...principleFixture, severityFilter: 'critical' });
  assert.match(md, /P-Crit/);
  assert.doesNotMatch(md, /P-Maj/);
  assert.doesNotMatch(md, /P-Min/);
  assert.doesNotMatch(md, /## Compliance Summary/);
  assert.match(md, /## Violations \(1\)/);
});

test("buildPrincipleReport with severityFilter='compliance' omits violations and shows compliance", () => {
  const md = buildPrincipleReport({ ...principleFixture, severityFilter: 'compliance' });
  assert.match(md, /## Violations \(0\)/);
  assert.match(md, /## Compliance Summary \(1\)/);
});

test("buildPrincipleReport with severityFilter='all' equals no filter", () => {
  const filtered = buildPrincipleReport({ ...principleFixture, severityFilter: 'all' });
  const unfiltered = buildPrincipleReport(principleFixture);
  assert.equal(filtered, unfiltered);
});

test('existing buildOverviewReport and buildDimensionReport still produce output', () => {
  const acc = { summary: { numericAverage: 8.0, overallGrade: 'B', totalViolations: 3, totalCompliance: 1, severity: { critical: 1, major: 1, minor: 1 } } };
  const md1 = buildOverviewReport(acc, dimensions, 'MyApp');
  assert.match(md1, /^# MyApp report/);
  const md2 = buildDimensionReport({
    evalData: { dimension: 'performance', compliance: [] },
    principleGrades: [{ principle: 'Speed', score: '8/10', grade: 'B' }],
    allViolations: dimensions[1].violations,
    overallGrade: { score: '8/10', grade: 'B' },
    dateLabel: '21 Apr 2025',
    runId: 'abc12345',
  });
  assert.match(md2, /^# performance report/);
});
