import test from 'node:test';
import assert from 'node:assert/strict';
import { buildFilePlanText, buildPrinciplePlanText } from './planTextBuilders.js';

const fileFixture = {
  file: 'src/foo/bar.js',
  violationsBySeverity: {
    critical: [{ severity: 'critical', principle: 'SRP', reason: 'Crit-1 reason', file: 'src/foo/bar.js', line: 1 }],
    major:    [{ severity: 'major',    principle: 'DRY', reason: 'Maj-1 reason', file: 'src/foo/bar.js', line: 2 }],
    minor:    [{ severity: 'minor',    principle: 'Style', reason: 'Min-1 reason', file: 'src/foo/bar.js', line: 3 }],
  },
};

test('buildFilePlanText with no severityFilter includes all severities', () => {
  const md = buildFilePlanText(fileFixture);
  assert.match(md, /Crit-1 reason/);
  assert.match(md, /Maj-1 reason/);
  assert.match(md, /Min-1 reason/);
  assert.match(md, /\*\*Total violations:\*\* 3/);
});

test("buildFilePlanText with severityFilter='critical' includes only critical", () => {
  const md = buildFilePlanText(fileFixture, 'critical');
  assert.match(md, /Crit-1 reason/);
  assert.doesNotMatch(md, /Maj-1 reason/);
  assert.doesNotMatch(md, /Min-1 reason/);
  assert.match(md, /\*\*Total violations:\*\* 1/);
});

test("buildFilePlanText with severityFilter='all' equals no filter", () => {
  assert.equal(buildFilePlanText(fileFixture, 'all'), buildFilePlanText(fileFixture));
});

test("buildFilePlanText with severityFilter='compliance' returns the empty-state body", () => {
  const md = buildFilePlanText(fileFixture, 'compliance');
  assert.equal(md, '_No violations match the current filter._');
});
