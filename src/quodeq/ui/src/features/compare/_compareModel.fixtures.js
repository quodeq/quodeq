/**
 * Shared fixtures for compareModel.*.test.js siblings.
 *
 * Split out of compareModel.test.js.
 */

export const NOW = '2026-08-25T12:00:00Z';

export const iso = (daysAgo) => new Date(Date.parse(NOW) - daysAgo * 86400000).toISOString();

export function makeSummary({ score = 7, dims = [], trend = [], lastRunDaysAgo = 1 } = {}) {
  return {
    summary: {
      numericAverage: score,
      overallGrade: 'Good',
      totalViolations: 10,
      totalCompliance: 90,
      severity: { critical: 1, major: 3, minor: 6 },
    },
    dimensions: dims,
    trend,
    runsCount: trend.length || 1,
    lastRun: { runId: 'r1', dateISO: iso(lastRunDaysAgo), status: 'complete' },
  };
}

export function makeProject(overrides = {}) {
  return {
    id: 'p1',
    name: 'proj-one',
    displayName: 'proj-one',
    languageStats: { py: 300, js: 40 },
    totalFiles: 500,
    analyzedFiles: 450,
    runsCount: 3,
    latestDate: iso(1),
    ...overrides,
  };
}

export const DIM_SEC = (score) => ({
  dimension: 'Security',
  overallScore: `${score}/10`,
  totals: { violationCount: 2, severity: { critical: 0, major: 1, minor: 1 } },
  principles: [
    { principle: 'Integrity', score: `${score}` },
    { principle: 'Confidentiality', score: `${Math.max(1, score - 1)}` },
  ],
});

export const DIM_USE = (score) => ({
  dimension: 'Usability',
  overallScore: `${score}/10`,
  totals: { violationCount: 1, severity: { critical: 0, major: 0, minor: 1 } },
  principles: [{ principle: 'Clarity', score: `${score}` }],
});
