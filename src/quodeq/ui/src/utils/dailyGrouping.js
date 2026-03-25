/**
 * Collapse trend entries (newest-first) into one entry per calendar day.
 * Keeps the first (newest) entry of each day, which has the most
 * up-to-date accumulated state.
 *
 * @param {Array} trend - Trend entries, newest first
 * @returns {Array} Collapsed entries, one per day
 */
export function collapseByDay(trend) {
  if (!trend || trend.length === 0) return trend;
  const collapsed = [];
  let currentDay = null;
  for (const entry of trend) {
    const datePart = (entry.dateISO || '').slice(0, 10);
    if (datePart !== currentDay) {
      currentDay = datePart;
      collapsed.push({ ...entry });
    }
  }
  return collapsed;
}

/**
 * Build a Set of dimension names evaluated on the selected day.
 * Scans all raw trend entries matching the selected date.
 *
 * @param {Array} trend - Raw trend entries (all runs)
 * @param {string} selectedRunId - The runId to find the selected day
 * @returns {Set<string>} Lowercase dimension names evaluated that day
 */
export function collectDayDimensions(trend, selectedRunId) {
  if (!trend || !trend.length || !selectedRunId) return new Set();
  const entry = trend.find((t) => t.runId === selectedRunId);
  if (!entry) return new Set();
  const selectedDate = (entry.dateISO || '').slice(0, 10);
  if (!selectedDate) return new Set();
  const names = new Set();
  for (const t of trend) {
    if ((t.dateISO || '').slice(0, 10) === selectedDate) {
      for (const d of t.dimensions || []) names.add(d.toLowerCase());
    }
  }
  return names;
}

/**
 * Build day-level available runs from raw available runs + trend.
 * Keeps the first (newest) run per calendar day.
 *
 * @param {Array} availableRuns - Raw available runs (newest first)
 * @param {Array} trend - Trend entries with dateISO
 * @returns {Array} One entry per day
 */
export function buildDailyRuns(availableRuns, trend) {
  if (!availableRuns || !availableRuns.length) return [];
  const byDay = [];
  let lastDate = null;
  for (const run of availableRuns) {
    const t = trend.find((r) => r.runId === run.runId);
    const datePart = (t?.dateISO || '').slice(0, 10);
    if (datePart !== lastDate) {
      byDay.push(run);
      lastDate = datePart;
    }
  }
  return byDay;
}
