import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { listProjects, listRuns, buildDashboard } from '../src/parsers/reportParser.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixturesRoot = path.join(__dirname, 'fixtures/evaluations');

test('listProjects returns projects with run metadata', () => {
  const projects = listProjects(fixturesRoot);
  assert.equal(projects.length, 1);
  assert.equal(projects[0].name, 'demo-app');
  assert.equal(projects[0].runsCount, 4);
  assert.equal(projects[0].latestRunId, '20260223');
});

test('listRuns sorts runs newest first and parses display date', () => {
  const runs = listRuns(fixturesRoot, 'demo-app');
  assert.equal(runs.length, 4);
  assert.equal(runs[0].runId, '20260223');
  assert.equal(runs[1].runId, '20260221');
  assert.match(runs[0].dateLabel, /Feb/);
});


test('parseSummaryRows handles decimal score "7.5/10 Good" and N/A grade gracefully', () => {
  const dashboard = buildDashboard(fixturesRoot, 'demo-app', '20260223');
  const dim = dashboard.dimensions[0];

  // Decimal score: "7.5/10 Good" → score="7.5/10", grade="Good"
  const mod = dim.principles.find((p) => p.name === 'Modularity');
  assert.ok(mod, 'Modularity principle should be parsed');
  assert.equal(mod.score, '7.5/10', 'decimal score should be extracted');
  assert.equal(mod.grade, 'Good', 'grade word should be separated from decimal score');

  // N/A cell should not produce a numeric score
  const ih = dim.principles.find((p) => p.name === 'Information Hiding');
  assert.ok(ih, 'Information Hiding principle should be parsed');
  assert.equal(ih.score, null, 'N/A cell should not produce a numeric score');

  // Overall "6/10 Adequate"
  assert.equal(dim.overallScore, '6/10');
  assert.equal(dim.overallGrade, 'Adequate');
});

test('parseSummaryRows extracts score and grade separately from combined "5/10 Adequate" cell', () => {
  const dashboard = buildDashboard(fixturesRoot, 'demo-app', '20260221');

  const dim = dashboard.dimensions[0];
  // Overall: "5.8/10 Adequate" → score must be "5.8/10", grade must be "Adequate"
  assert.equal(dim.overallScore, '5.8/10', 'overall score should be extracted from combined cell');
  assert.equal(dim.overallGrade, 'Adequate', 'overall grade should be the word, not the full combined string');

  // Per-principle: "5/10 Adequate" → score="5/10", grade="Adequate"
  const sr = dim.principles.find((p) => p.name === 'Single Responsibility');
  assert.ok(sr, 'Single Responsibility principle should be parsed');
  assert.equal(sr.score, '5/10', 'principle score should be extracted');
  assert.equal(sr.grade, 'Adequate', 'principle grade should be the word only');

  const mod = dim.principles.find((p) => p.name === 'Modularity');
  assert.ok(mod, 'Modularity principle should be parsed');
  assert.equal(mod.score, '7/10', 'modularity score should be extracted');
  assert.equal(mod.grade, 'Good', 'modularity grade should be the word only');
});

test('parseDetailedFindings handles em dash separator (sonnet 4.6 format)', () => {
  const dashboard = buildDashboard(fixturesRoot, 'demo-app', '20260221');

  const dim = dashboard.dimensions[0];
  assert.equal(dim.dimension, 'maintainability');
  // Violations must be found under the em-dash headings
  assert.ok(dim.violations.length > 0, 'expected violations to be parsed from em-dash headings');
  assert.equal(dim.violations[0].principle, 'Single Responsibility');
  assert.equal(dim.violations[0].file, 'src/api/router.js');
  assert.equal(dim.violations[0].line, 28);
  // Compliance evidence must also be extracted
  assert.ok(dim.compliance.length > 0, 'expected compliance entries to be parsed from em-dash headings');
  assert.equal(dim.compliance[0].principle, 'Single Responsibility');
  assert.equal(dim.compliance[0].file, 'src/utils/logger.js');
});

test('buildDashboard returns summary, dimensions and trend for specific run', () => {
  const dashboard = buildDashboard(fixturesRoot, 'demo-app', '20260220');

  assert.equal(dashboard.project, 'demo-app');
  assert.equal(dashboard.selectedRun.runId, '20260220');
  assert.equal(dashboard.summary.dimensionsCount, 1);
  assert.equal(dashboard.summary.overallGrade, 'Proficient');
  assert.equal(dashboard.dimensions[0].dimension, 'maintainability');
  assert.equal(dashboard.dimensions[0].totals.violationCount, 1);
  assert.equal(dashboard.dimensions[0].totals.complianceCount, 1);
  assert.equal(dashboard.dimensions[0].totals.severity.critical, 1);
  assert.equal(dashboard.dimensions[0].totals.severity.major, 0);
  assert.equal(dashboard.dimensions[0].totals.severity.minor, 0);
  assert.equal(dashboard.dimensions[0].violations[0].principle, 'Single Responsibility');
  assert.equal(dashboard.dimensions[0].violations[0].file, 'src/api/router.js');
  assert.equal(dashboard.dimensions[0].violations[0].line, 28);
  assert.equal(dashboard.dimensions[0].compliance[0].file, 'src/utils/logger.js');
  assert.equal(dashboard.trend.length, 4);
  assert.equal(dashboard.trend[0].runId, '20260223');
});
