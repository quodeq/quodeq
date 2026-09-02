/**
 * Shared fixtures for dailyGrouping.*.test.js siblings.
 *
 * Split out of dailyGrouping.test.js.
 */

export const TREND = [
  { runId: 'r1', dateISO: '2026-03-25T14:00:00', numericAverage: 9.5, overallGrade: 'Exemplary', dimensions: ['maintainability'] },
  { runId: 'r2', dateISO: '2026-03-25T10:00:00', numericAverage: 9.3, overallGrade: 'Exemplary', dimensions: ['security'] },
  { runId: 'r3', dateISO: '2026-03-24T18:00:00', numericAverage: 9.0, overallGrade: 'Exemplary', dimensions: ['maintainability', 'reliability'] },
  { runId: 'r4', dateISO: '2026-03-24T08:00:00', numericAverage: 8.8, overallGrade: 'Good', dimensions: ['security'] },
  { runId: 'r5', dateISO: '2026-03-23T12:00:00', numericAverage: 8.5, overallGrade: 'Good', dimensions: ['maintainability'] },
];

export const AVAILABLE_RUNS = [
  { runId: 'r1', dateLabel: '2026-03-25' },
  { runId: 'r2', dateLabel: '2026-03-25' },
  { runId: 'r3', dateLabel: '2026-03-24' },
  { runId: 'r4', dateLabel: '2026-03-24' },
  { runId: 'r5', dateLabel: '2026-03-23' },
];

export const TREND_WITH_RUNNING = [
  { runId: 'live', dateISO: '2026-03-25T16:00:00', status: 'in_progress', numericAverage: 5.1, dimensions: ['security'], dimensionDetails: [{ dimension: 'security', score: 5.1 }] },
  { runId: 'done2', dateISO: '2026-03-25T10:00:00', status: 'complete', numericAverage: 9.2, dimensions: ['maintainability'], dimensionDetails: [{ dimension: 'maintainability', score: 9.2 }] },
  { runId: 'done1', dateISO: '2026-03-24T10:00:00', status: 'complete', numericAverage: 8.0, dimensions: ['security'], dimensionDetails: [{ dimension: 'security', score: 8.0 }] },
];

// Runs spanning 3 days / 3 ISO-weeks / 3 months (newest-first).
export const MULTI = [
  { runId: 'm1', dateISO: '2026-05-02T12:00:00', dimensions: ['security'] },        // Sat W18, 2026-05
  { runId: 'm2', dateISO: '2026-04-14T18:00:00', dimensions: ['maintainability'] }, // Tue W16, 2026-04
  { runId: 'm3', dateISO: '2026-04-14T09:00:00', dimensions: ['reliability'] },     // Tue W16 (older same day)
  { runId: 'm4', dateISO: '2026-03-25T14:00:00', dimensions: ['security'] },        // Wed W13, 2026-03
  { runId: 'm5', dateISO: '2026-03-23T10:00:00', dimensions: ['performance'] },     // Mon W13, 2026-03
];

export const MULTI_RUNS = [
  { runId: 'm1', dateLabel: '2 May 2026' },
  { runId: 'm2', dateLabel: '14 Apr 2026' },
  { runId: 'm3', dateLabel: '14 Apr 2026' },
  { runId: 'm4', dateLabel: '25 Mar 2026' },
  { runId: 'm5', dateLabel: '23 Mar 2026' },
];

// Newest-first, entries carry per-dimension scores.
export const DIM_TREND = [
  { runId: 'd1', dateISO: '2026-05-02T12:00:00', dateLabel: '2 May',  overallGrade: 'Exemplary', dimensionDetails: [{ dimension: 'security', score: 9.0 }] },                                            // May, W18
  { runId: 'd2', dateISO: '2026-04-14T18:00:00', dateLabel: '14 Apr', overallGrade: 'Good',      dimensionDetails: [{ dimension: 'maintainability', score: 8.0, grade: 'Good' }] },                       // Apr, W16 (newest in week)
  { runId: 'd3', dateISO: '2026-04-13T09:00:00', dateLabel: '13 Apr', overallGrade: 'Good',      dimensionDetails: [{ dimension: 'maintainability', score: 7.0 }] },                                       // Apr, W16 (older same week)
  { runId: 'd4', dateISO: '2026-03-25T14:00:00', dateLabel: '25 Mar', overallGrade: 'Good',      dimensionDetails: [{ dimension: 'security', score: 6.0 }, { dimension: 'maintainability', score: 6.5 }] },// Mar, W13
  { runId: 'd5', dateISO: '2026-03-23T10:00:00', dateLabel: '23 Mar', overallGrade: 'Good',      dimensionDetails: [{ dimension: 'maintainability', score: 6.0 }] },                                       // Mar, W13 (older)
];

/** The local calendar day the UI displays for an instant (what
 * formatShortDate/toLocaleDateString render), as YYYY-MM-DD. */
export function displayedLocalDay(iso) {
  const d = new Date(iso);
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, '0'),
    String(d.getDate()).padStart(2, '0'),
  ].join('-');
}
