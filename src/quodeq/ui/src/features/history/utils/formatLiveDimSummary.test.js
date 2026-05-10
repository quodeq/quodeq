import test from 'node:test';
import assert from 'node:assert/strict';
import { formatLiveDimSummary } from './formatLiveDimSummary.js';

test('returns empty-state placeholder for empty live dims', () => {
  assert.equal(formatLiveDimSummary({}, ['security', 'maintainability']), '');
  assert.equal(formatLiveDimSummary(null, []), '');
  assert.equal(formatLiveDimSummary(undefined, undefined), '');
});

test('formats a partial run (1 of 3 dims complete)', () => {
  const live = { security: { dimension: 'security', score: 7.4 } };
  const planned = ['security', 'maintainability', 'performance'];
  assert.equal(formatLiveDimSummary(live, planned), '1 / 3 dims · sec 7.4');
});

test('formats two completed of three planned', () => {
  const live = {
    security: { dimension: 'security', score: 7.4 },
    maintainability: { dimension: 'maintainability', score: 6.1 },
  };
  const planned = ['security', 'maintainability', 'performance'];
  assert.equal(
    formatLiveDimSummary(live, planned),
    '2 / 3 dims · sec 7.4, maint 6.1',
  );
});

test('formats all-complete-but-not-yet-terminal', () => {
  const live = {
    security: { dimension: 'security', score: 7.4 },
    maintainability: { dimension: 'maintainability', score: 6.1 },
  };
  const planned = ['security', 'maintainability'];
  assert.equal(
    formatLiveDimSummary(live, planned),
    '2 / 2 dims · sec 7.4, maint 6.1',
  );
});

test('falls back to average_score when score field is missing', () => {
  const live = {
    security: { dimension: 'security', average_score: 8.25 },
  };
  assert.equal(formatLiveDimSummary(live, ['security']), '1 / 1 dims · sec 8.3');
});

test('renders dim without a score when both fields are missing', () => {
  const live = { security: { dimension: 'security' } };
  assert.equal(formatLiveDimSummary(live, ['security']), '1 / 1 dims · sec');
});

test('falls back to live count when plannedDimensions is missing', () => {
  const live = { security: { dimension: 'security', score: 7.4 } };
  assert.equal(formatLiveDimSummary(live, undefined), '1 / 1 dims · sec 7.4');
  assert.equal(formatLiveDimSummary(live, []), '1 / 1 dims · sec 7.4');
});

test('skips entries that have no dimension name', () => {
  const live = {
    security: { dimension: 'security', score: 7.4 },
    _: { score: 5 }, // malformed -- no dimension field
  };
  assert.equal(formatLiveDimSummary(live, ['security']), '1 / 1 dims · sec 7.4');
});
