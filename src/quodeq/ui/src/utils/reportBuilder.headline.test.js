import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildRunReport, buildOverviewReport } from './reportBuilder.js';
import { buildHeadlineLine, buildSinceBaselineSection } from './reportBuilder/headline.js';

const headline = { majors: 3, critical: 0, openTypes: 37, violations: 1738, filesRead: 2525, sourceFileCount: 2660, density: 68.8, coveragePct: 95 };
const since = { majorsDelta: -2, typesClosed: ['M-MDF-1', 'M-ANA-1'], typesOpened: [], newCount: 4, resolvedCount: 7, scope: 'changed-files', changedFiles: 12, againstRunIds: ['r0'], againstCommitShas: ['c9b5370abc'] };
const runSummary = { overallGrade: 'Exemplary', numericAverage: '9.0', totalViolations: 1738, totalCompliance: 2207, severity: { critical: 0, major: 3, minor: 1735 } };
const dashboard = { dimensions: [], selectedRun: { runId: 'abc12345', dateLabel: '26 Sep 2026', commitSha: 'ab00c6b11' } };

test('the headline line follows the hero order', () => {
  const line = buildHeadlineLine({ headline, score: '9.0/10', grade: 'Exemplary' });
  assert.equal(line, '**Majors:** 3 (0 critical) · **Open types:** 37 · **Score:** 9.0/10 Exemplary · **Density:** 68.8 per 100 files read (95% coverage)');
});

test('headline line without files read or baseline', () => {
  const line = buildHeadlineLine({ headline: { ...headline, density: null, coveragePct: null }, score: '9.0/10', grade: 'Exemplary' });
  assert.match(line, /\*\*Density:\*\* -$/);
  assert.deepEqual(buildSinceBaselineSection(null), []);
  const md = buildRunReport({ dashboard, runSummary, projectName: 'MyApp', headline: { ...headline, density: null, coveragePct: null }, since: null });
  assert.doesNotMatch(md, /## Since baseline/);
  assert.doesNotMatch(md, /Overall Score/);
});

test('the run report carries the headline and a since-baseline section, and keeps the total in the summary', () => {
  const md = buildRunReport({ dashboard, runSummary, projectName: 'MyApp', headline, since, selectedRun: dashboard.selectedRun });
  assert.match(md, /^\*\*Date:\*\* 26 Sep 2026 · \*\*Run:\*\* abc12345$/m);
  assert.match(md, /^\*\*Majors:\*\* 3 \(0 critical\) · \*\*Open types:\*\* 37 · \*\*Score:\*\* 9\/10 Exemplary/m);
  assert.match(md, /## Since baseline/);
  assert.match(md, /run c9b5370 to ab00c6b · 12 files changed/);
  assert.match(md, /majors -2 · types closed M-MDF-1, M-ANA-1 · types opened none/);
  assert.match(md, /new in changed files 4 · resolved 7/);
  assert.match(md, /\*\*1738\*\* total violations/);
});

test('an unchanged tree gets one sentence; all-files scope is named', () => {
  const quiet = buildSinceBaselineSection({ ...since, majorsDelta: 0, typesClosed: [], typesOpened: [], newCount: 0, resolvedCount: 0, changedFiles: 0 });
  assert.ok(quiet.join('\n').includes('No changes since the baseline.'));
  const all = buildSinceBaselineSection({ ...since, scope: 'all', changedFiles: null });
  assert.ok(all.join('\n').includes('in all files (no commit recorded or the tree had uncommitted changes)'));
  assert.ok(all.join('\n').includes('new in all files 4'));
});

test('the overview report takes the same headline and since', () => {
  const md = buildOverviewReport({ summary: runSummary }, [], 'MyApp', { headline, since });
  assert.match(md, /\*\*Open types:\*\* 37/);
  assert.match(md, /## Since baseline/);
});
