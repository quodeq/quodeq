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

const principleViolations = [
  { severity: 'critical', principle: 'SRP', reason: 'P-Crit', file: 'a.js', line: 1 },
  { severity: 'major',    principle: 'SRP', reason: 'P-Maj',  file: 'b.js', line: 2 },
  { severity: 'minor',    principle: 'SRP', reason: 'P-Min',  file: 'c.js', line: 3 },
];
const principleBySeverity = {
  critical: [principleViolations[0]],
  major:    [principleViolations[1]],
  minor:    [principleViolations[2]],
};

test('buildPrinciplePlanText with no severityFilter includes all severities (object form)', () => {
  const md = buildPrinciplePlanText({ principle: 'SRP', violations: principleViolations });
  assert.match(md, /P-Crit/);
  assert.match(md, /P-Maj/);
  assert.match(md, /P-Min/);
});

test("buildPrinciplePlanText with severityFilter='critical' includes only critical (split form)", () => {
  const md = buildPrinciplePlanText('SRP', principleViolations, principleBySeverity, undefined, 'critical');
  assert.match(md, /P-Crit/);
  assert.doesNotMatch(md, /P-Maj/);
  assert.doesNotMatch(md, /P-Min/);
  assert.match(md, /\*\*Total violations:\*\* 1/);
});

test("buildPrinciplePlanText with severityFilter='all' equals no filter (split form)", () => {
  const a = buildPrinciplePlanText('SRP', principleViolations, principleBySeverity, undefined, 'all');
  const b = buildPrinciplePlanText('SRP', principleViolations, principleBySeverity);
  assert.equal(a, b);
});

test("buildPrinciplePlanText with severityFilter='compliance' returns the empty-state body", () => {
  const md = buildPrinciplePlanText('SRP', principleViolations, principleBySeverity, undefined, 'compliance');
  assert.equal(md, '_No violations match the current filter._');
});

test("buildPrinciplePlanText object form ignores severityFilter (it's split-form only)", () => {
  // The object form does not take a positional severityFilter; consumers
  // using the object form pre-filter their input. This pins down that
  // calling the object form does not crash and renders all the violations
  // it was given.
  const md = buildPrinciplePlanText({ principle: 'SRP', violations: principleViolations.slice(0, 1) });
  assert.match(md, /P-Crit/);
  assert.doesNotMatch(md, /P-Maj/);
});
