import { isoWeekKey, localDayKey } from './dailyGrouping.js';
import { LOCALE, t } from '../strings/index.js';

// Intl formatters are comparatively expensive to construct, and these run in
// list renders. Build once at module scope.
const DAY_MONTH_YEAR = new Intl.DateTimeFormat(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' });
const MONTH_YEAR = new Intl.DateTimeFormat(LOCALE, { month: 'long', year: 'numeric' });

/**
 * Format a date string as "20 Feb 2026" (day + abbreviated month + year).
 * Falls back to the original string if it cannot be parsed as a date.
 *
 * @param {string|null|undefined} dateStr
 * @returns {string}
 */
export function formatShortDate(dateStr) {
  if (!dateStr) return dateStr;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return DAY_MONTH_YEAR.format(d);
}

/**
 * Format a run identifier for display.
 * - If a dateLabel is provided, use it directly.
 * - "latest" (or falsy) becomes "Latest".
 * - Otherwise return a truncated UUID as fallback.
 *
 * @param {string|null|undefined} runId
 * @param {string|null|undefined} dateLabel
 * @returns {string}
 */
export function formatRunId(runId, dateLabel) {
  if (dateLabel) return dateLabel;
  if (!runId || runId === 'latest') return 'Latest';
  // Truncate UUID for compact display
  const s = String(runId);
  return s.length > 8 ? s.slice(0, 8) + '…' : s;
}

/**
 * Human-readable duration from seconds: "42s", "12m 34s", "4h 15m 12s".
 * Floors to whole seconds so a ticking clock advances evenly; "—" when the
 * value is unknown.
 *
 * @param {number|null|undefined} s
 * @returns {string}
 */
export function formatDuration(s) {
  if (s == null || !Number.isFinite(s)) return '—';
  const total = Math.max(0, Math.floor(s));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  if (h > 0) return `${h}h ${m}m ${sec}s`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

/**
 * Duration for round targets like time budgets: zero components are dropped
 * ("2h", "1h 30m", "45m"), so a 2-hour budget never reads "2h 0m 0s". Seconds
 * appear only under a minute.
 *
 * @param {number|null|undefined} s
 * @returns {string}
 */
export function formatDurationCoarse(s) {
  if (s == null || !Number.isFinite(s)) return '—';
  const total = Math.max(0, Math.round(s));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const parts = [];
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  if (parts.length === 0) parts.push(`${total % 60}s`);
  return parts.join(' ');
}

/**
 * Human label for a score-history bucket at the given grouping granularity.
 * - day   -> the entry's LOCAL date (e.g. "25 Mar 2026")
 * - month -> "March 2026" (from the local calendar day)
 * - week  -> "Week 13, 2026" (ISO week of the local calendar day)
 * Falls back to the entry's dateLabel (then dateISO) when unparseable.
 *
 * All three derive from the same local-day key the grouping uses
 * (bucketKey/localDayKey), so a run's label always names the bucket it
 * sits in. The server's dateLabel is UTC-rendered and disagrees with the
 * local day for runs near midnight; it is only a fallback here.
 *
 * @param {{ dateISO?: string, dateLabel?: string }} entry
 * @param {'day'|'week'|'month'} [granularity='day']
 * @returns {string}
 */
export function formatPeriodLabel(entry, granularity = 'day') {
  const iso = entry?.dateISO || '';
  const fallback = entry?.dateLabel || iso;
  if (granularity === 'month') {
    const [y, m] = localDayKey(iso).slice(0, 7).split('-');
    if (!y || !m) return fallback;
    // Format the local calendar day, not the raw instant: the bucket is a
    // local-day key, so a run near midnight must name the bucket it sits in.
    const d = new Date(Number(y), Number(m) - 1, 1);
    return Number.isNaN(d.getTime()) ? fallback : MONTH_YEAR.format(d);
  }
  if (granularity === 'week') {
    const key = isoWeekKey(iso); // 'YYYY-Www' or ''
    const [y, w] = key.split('-W');
    // Intl has no week-of-year format, so this one stays a catalog pattern.
    return (y && w) ? t('common.weekOfYear', { week: Number(w), year: y }) : fallback;
  }
  if (iso.length > 10) {
    const d = new Date(iso);
    if (!Number.isNaN(d.getTime())) return DAY_MONTH_YEAR.format(d);
  }
  return fallback;
}
