import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildRunReport, buildOverviewReport } from './reportBuilder.js';
import { buildTilesLine, buildStripLine, buildSinceBaselineSection } from './reportBuilder/headline.js';

const headline = { majors: 3, critical: 0, openTypes: 37, violations: 1738, filesRead: 2525, sourceFileCount: 2660, density: 68.8, coveragePct: 95 };
const since = { majorsDelta: -2, typesClosed: ['M-MDF-1', 'M-ANA-1'], typesOpened: [], newCount: 4, resolvedCount: 7, scope: 'changed-files', changedFiles: 12, againstRunIds: ['r0'], againstCommitShas: ['c9b5370abc'] };
const runSummary = { overallGrade: 'Exemplary', numericAverage: '9.0', totalViolations: 1738, totalCompliance: 2207, severity: { critical: 0, major: 3, minor: 1735 } };
const dashboard = { dimensions: [], selectedRun: { runId: 'abc12345', dateLabel: '26 Sep 2026', commitSha: 'ab00c6b11' } };

test('the tiles line follows the hero: score, violations, compliance, ratio', () => {
  const line = buildTilesLine({ summary: runSummary, score: '9.0/10', grade: 'Exemplary' });
  assert.equal(line, '**Score:** 9.0/10 Exemplary · **Violations:** 1738 · **Compliance:** 2207 · **Ratio:** 1:1');
});

test('the tiles line without totals is the score alone', () => {
  assert.equal(buildTilesLine({ summary: {}, score: '9.0/10', grade: 'Exemplary' }), '**Score:** 9.0/10 Exemplary');
});

test('the strip line follows the strip: critical, majors, open types, density', () => {
  assert.equal(buildStripLine(headline), '**Critical:** 0 · **Majors:** 3 · **Open types:** 37 · **Density:** 68.8 per 100 files read (95% coverage)');
  assert.equal(buildStripLine(null), '');
});

test('the strip line names majors without the criticals, like the strip on screen', () => {
  const line = buildStripLine({ ...headline, critical: 2, majors: 5 });
  assert.match(line, /^\*\*Critical:\*\* 2 · \*\*Majors:\*\* 3 · /);
});

test('a missing density reads as words, never a dash', () => {
  const line = buildStripLine({ ...headline, density: null, coveragePct: null });
  assert.match(line, /\*\*Density:\*\* not available \(no files-read count\)$/);
  assert.doesNotMatch(line, /\*\* -/);
});

test('headline line without a headline or a baseline', () => {
  assert.deepEqual(buildSinceBaselineSection(null), []);
  const md = buildRunReport({ dashboard, runSummary, projectName: 'MyApp' });
  assert.match(md, /^\*\*Score:\*\* 9\/10 Exemplary · \*\*Violations:\*\* 1738/m);
  assert.doesNotMatch(md, /## Since baseline/);
  assert.doesNotMatch(md, /Overall Score/);
  assert.doesNotMatch(md, /\*\*Critical:\*\*/);
});

test('the run report: tiles, then the strip, then since baseline with counts only', () => {
  const md = buildRunReport({ dashboard, runSummary, projectName: 'MyApp', headline, since });
  assert.match(md, /^\*\*Date:\*\* 26 Sep 2026 · \*\*Run:\*\* abc12345$/m);
  const tiles = md.indexOf('**Score:**');
  const strip = md.indexOf('**Critical:** 0 · **Majors:** 3 · **Open types:** 37');
  const sinceAt = md.indexOf('## Since baseline');
  assert.ok(tiles > 0 && tiles < strip && strip < sinceAt);
  assert.match(md, /run c9b5370 to ab00c6b · 12 files changed/);
  assert.match(md, /majors -2 · types closed 2 · types opened 0/);
  assert.match(md, /new in changed files 4 · resolved 7/);
  assert.doesNotMatch(md, /M-MDF-1/);
  assert.match(md, /\*\*1738\*\* total violations/);
});

test('an unchanged tree gets one sentence; all-files scope is named', () => {
  const quiet = buildSinceBaselineSection({ ...since, majorsDelta: 0, typesClosed: [], typesOpened: [], newCount: 0, resolvedCount: 0, changedFiles: 0 });
  assert.ok(quiet.join('\n').includes('No changes since the baseline.'));
  const all = buildSinceBaselineSection({ ...since, scope: 'all', changedFiles: null });
  assert.ok(all.join('\n').includes('in all files (no commit recorded or the tree had uncommitted changes)'));
  assert.ok(all.join('\n').includes('new in all files 4'));
});

test('a mixed scope names its own reason, like the strip', () => {
  const mixed = buildSinceBaselineSection({ ...since, scope: 'mixed', changedFiles: null, againstRunIds: ['r0', 'r1'] }).join('\n');
  assert.ok(mixed.includes('against 2 baseline runs · in all files (baselines differ per dimension)'));
  assert.ok(!mixed.includes('no commit recorded'));
});

test('the overview report takes the same headline and since', () => {
  const md = buildOverviewReport({ summary: runSummary }, [], 'MyApp', { headline, since });
  assert.match(md, /\*\*Open types:\*\* 37/);
  assert.match(md, /## Since baseline/);
});
