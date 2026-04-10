import test from 'node:test';
import assert from 'node:assert/strict';
import { severityColor, complianceRateColor, healthColor, worstSeverity } from '../viz/core/mapColors.js';

test('severityColor returns correct colors', () => {
  assert.equal(severityColor('critical'), 'var(--color-sev-critical-text)');
  assert.equal(severityColor('major'), 'var(--color-sev-major-text)');
  assert.equal(severityColor('minor'), 'var(--color-sev-minor-text)');
  assert.equal(severityColor(null), 'var(--color-compliance)');
});

test('complianceRateColor maps rate to gradient', () => {
  assert.equal(complianceRateColor(1.0), 'var(--color-compliance)');
  assert.equal(complianceRateColor(0.75), 'var(--color-sev-minor-text)');
  assert.equal(complianceRateColor(0.5), 'var(--color-sev-major-text)');
  assert.equal(complianceRateColor(0.2), 'var(--color-sev-critical-text)');
});

test('healthColor maps ratio to gradient', () => {
  assert.equal(healthColor(0.9), 'var(--color-compliance)');
  assert.equal(healthColor(0.2), 'var(--color-sev-critical-text)');
});

test('worstSeverity returns highest severity from breakdown', () => {
  assert.equal(worstSeverity({ critical: 1, major: 0, minor: 0 }), 'critical');
  assert.equal(worstSeverity({ critical: 0, major: 2, minor: 1 }), 'major');
  assert.equal(worstSeverity({ critical: 0, major: 0, minor: 3 }), 'minor');
  assert.equal(worstSeverity({ critical: 0, major: 0, minor: 0 }), null);
});
