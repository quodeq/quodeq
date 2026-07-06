/**
 * ISO-8601 week key (Monday start; week 1 contains the first Thursday).
 * Operates timezone-naively on the YYYY-MM-DD prefix via Date.UTC, matching
 * how the day grouping slices the date string.
 *
 * @param {string} dateISO
 * @returns {string} e.g. "2026-W13", or "" when the date is missing/invalid
 */
export function isoWeekKey(dateISO) {
  const datePart = (dateISO || '').slice(0, 10);
  const [y, m, d] = datePart.split('-').map(Number);
  if (!y || !m || !d) return '';
  const date = new Date(Date.UTC(y, m - 1, d));
  const dayNum = date.getUTCDay() || 7;           // Mon=1 .. Sun=7
  date.setUTCDate(date.getUTCDate() + 4 - dayNum); // shift to this week's Thursday
  const isoYear = date.getUTCFullYear();
  const yearStart = new Date(Date.UTC(isoYear, 0, 1));
  const weekNo = Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
  return `${isoYear}-W${String(weekNo).padStart(2, '0')}`;
}

/**
 * Bucket key for a trend/run entry's date at the given granularity.
 * Empty dates produce "" (their own group), matching legacy day behavior.
 *
 * @param {string} dateISO
 * @param {'day'|'week'|'month'} [granularity='day']
 * @returns {string}
 */
export function bucketKey(dateISO, granularity = 'day') {
  if (granularity === 'month') return (dateISO || '').slice(0, 7);
  if (granularity === 'week') return isoWeekKey(dateISO);
  return (dateISO || '').slice(0, 10);
}

/**
 * Collapse trend entries (newest-first) into one entry per period bucket,
 * keeping the first (newest) entry of each bucket — the most up-to-date
 * accumulated state for that period.
 *
 * @param {Array} trend - Trend entries, newest first
 * @param {'day'|'week'|'month'} [granularity='day']
 * @returns {Array} Collapsed entries, one per bucket
 */
export function collapseByPeriod(trend, granularity = 'day') {
  if (!trend || trend.length === 0) return trend;
  const collapsed = [];
  let currentKey = null;
  for (const entry of trend) {
    const key = bucketKey(entry.dateISO, granularity);
    if (key !== currentKey) {
      currentKey = key;
      collapsed.push({ ...entry });
    }
  }
  return collapsed;
}

/**
 * Build a Set of dimension names evaluated in the selected run's period.
 *
 * @param {Array} trend - Raw trend entries (all runs)
 * @param {string} selectedRunId
 * @param {'day'|'week'|'month'} [granularity='day']
 * @returns {Set<string>} Lowercase dimension names evaluated that period
 */
export function collectPeriodDimensions(trend, selectedRunId, granularity = 'day') {
  if (!trend || !trend.length || !selectedRunId) return new Set();
  const entry = trend.find((t) => t.runId === selectedRunId);
  if (!entry) return new Set();
  const selectedKey = bucketKey(entry.dateISO, granularity);
  if (!selectedKey) return new Set();
  const names = new Set();
  for (const t of trend) {
    if (bucketKey(t.dateISO, granularity) === selectedKey) {
      for (const dim of t.dimensions || []) names.add(dim.toLowerCase());
    }
  }
  return names;
}

/**
 * Build period-level available runs, keeping the first (newest) run per bucket.
 *
 * @param {Array} availableRuns - Raw available runs (newest first)
 * @param {Array} trend - Trend entries with dateISO
 * @param {'day'|'week'|'month'} [granularity='day']
 * @returns {Array} One run per bucket
 */
export function buildPeriodRuns(availableRuns, trend, granularity = 'day') {
  if (!availableRuns || !availableRuns.length) return [];
  const trendMap = new Map(trend.map((r) => [r.runId, r]));
  const byBucket = [];
  let lastKey = null;
  for (const run of availableRuns) {
    const t = trendMap.get(run.runId);
    const key = bucketKey(t?.dateISO, granularity);
    if (key !== lastKey) {
      byBucket.push(run);
      lastKey = key;
    }
  }
  return byBucket;
}

/**
 * Per-dimension score series collapsed to one entry per period bucket.
 *
 * Walks the trend newest-first; for each bucket keeps the newest run that
 * actually scored `dimensionName` (so a bucket whose newest run skipped the
 * dimension still surfaces the newest run in that bucket that did score it).
 * Buckets are keyed by bucketKey(dateISO, granularity); entries without a
 * usable date share the empty-key bucket. Returns oldest-first so callers read
 * left-to-right chronologically.
 *
 * @param {Array} trend            Trend entries, newest-first.
 * @param {string} dimensionName   Case-insensitive match.
 * @param {'day'|'week'|'month'} [granularity='day']
 * @param {number} [limit=Infinity] Max buckets to keep (newest buckets win).
 * @returns {Array<{runId:string, dateISO:string, dateLabel:string, score:number, grade:*, overallGrade:*}>}
 */
export function extractDimensionPeriodSeries(trend, dimensionName, granularity = 'day', limit = Infinity) {
  if (!Array.isArray(trend) || !dimensionName) return [];
  const want = String(dimensionName).toLowerCase();
  const seen = new Set();
  const out = [];
  for (const entry of trend) {
    const key = bucketKey(entry?.dateISO, granularity);
    if (seen.has(key)) continue;
    const details = entry?.dimensionDetails;
    if (!Array.isArray(details)) continue;
    const match = details.find((d) => (d.dimension || '').toLowerCase() === want);
    const score = match ? parseFloat(match.score) : NaN;
    if (!Number.isFinite(score)) continue;
    seen.add(key);
    out.push({
      runId: entry.runId,
      dateISO: entry.dateISO,
      dateLabel: entry.dateLabel,
      score,
      grade: match.grade,
      overallGrade: entry.overallGrade,
    });
    if (out.length >= limit) break;
  }
  return out.reverse();
}

// ── Day-named wrappers (preserve existing call sites and tests) ─────────────
/**
 * Collapse trend entries (newest-first) into one entry per calendar day.
 * Keeps the first (newest) entry of each day, which has the most
 * up-to-date accumulated state.
 *
 * @param {Array} trend - Trend entries, newest first
 * @returns {Array} Collapsed entries, one per day
 */
export function collapseByDay(trend) {
  return collapseByPeriod(trend, 'day');
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
  return collectPeriodDimensions(trend, selectedRunId, 'day');
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
  return buildPeriodRuns(availableRuns, trend, 'day');
}
