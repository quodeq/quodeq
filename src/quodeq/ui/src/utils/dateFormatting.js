import { isoWeekKey, localDayKey, YEAR_MONTH_KEY_LENGTH } from './dailyGrouping.js';
import { LOCALE, t } from '../strings/index.js';
import { SECONDS_PER_HOUR } from './time.js';
import { GRANULARITY } from './granularity.js';
import { LATEST_RUN_ID } from '../constants.js';

const DEFAULT_CALLER_NAME = 'dateFormatting'; // default `where` tag for the warn-log callers below

// Intl formatters are comparatively expensive to construct, and these run in
// list renders. Build once at module scope.
const DAY_MONTH_YEAR = new Intl.DateTimeFormat(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' });
const MONTH_YEAR = new Intl.DateTimeFormat(LOCALE, { month: 'long', year: 'numeric' });
const RUN_ID_TRUNCATE_LENGTH = 8;

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
  if (!runId || runId === LATEST_RUN_ID) return 'Latest';
  // Truncate UUID for compact display
  const s = String(runId);
  return s.length > RUN_ID_TRUNCATE_LENGTH ? s.slice(0, RUN_ID_TRUNCATE_LENGTH) + '…' : s;
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
  const h = Math.floor(total / SECONDS_PER_HOUR);
  const m = Math.floor((total % SECONDS_PER_HOUR) / 60);
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
  const h = Math.floor(total / SECONDS_PER_HOUR);
  const m = Math.floor((total % SECONDS_PER_HOUR) / 60);
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
export function formatPeriodLabel(entry, granularity = GRANULARITY.DAY) {
  const iso = entry?.dateISO || '';
  const fallback = entry?.dateLabel || iso;
  if (granularity === GRANULARITY.MONTH) {
    const [y, m] = localDayKey(iso).slice(0, YEAR_MONTH_KEY_LENGTH).split('-');
    if (!y || !m) return fallback;
    // Format the local calendar day, not the raw instant: the bucket is a
    // local-day key, so a run near midnight must name the bucket it sits in.
    const d = new Date(Number(y), Number(m) - 1, 1);
    return Number.isNaN(d.getTime()) ? fallback : MONTH_YEAR.format(d);
  }
  if (granularity === GRANULARITY.WEEK) {
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

// The long forms the run views show: "12 February 2026" and "14:05". These
// go through Date's own toLocale* methods rather than a cached Intl
// formatter: an unparseable date renders as "Invalid Date" there instead of
// throwing, which is what the run rows have always shown.
const DAY_LONG_MONTH_YEAR_OPTS = { day: 'numeric', month: 'long', year: 'numeric' };
const HOUR_MINUTE_OPTS = { hour: '2-digit', minute: '2-digit' };

/**
 * A run's date as "12 February 2026".
 *
 * Every caller renders an unparseable date as its own fallback rather than
 * crashing a row, so a failure is logged and `fallback` returned.
 *
 * @param {string|null|undefined} dateISO
 * @param {string} [fallback=''] Returned for a missing or unformattable date.
 * @param {string} [where='dateFormatting'] Names the caller in the warning.
 * @returns {string}
 */
export function formatRunDate(dateISO, fallback = '', where = DEFAULT_CALLER_NAME) {
  if (!dateISO) return fallback;
  try {
    return new Date(dateISO).toLocaleDateString(LOCALE, DAY_LONG_MONTH_YEAR_OPTS);
  } catch (err) {
    console.warn(`[${where}] date format failed:`, err);
    return fallback;
  }
}

/**
 * A run's date and time of day as "12 February 2026 14:05", the run
 * navigator's label. One try around both halves: if either throws, the whole
 * label falls back rather than showing half a date.
 *
 * @param {string|null|undefined} dateISO
 * @param {string} [fallback=''] Returned for a missing or unformattable date.
 * @param {string} [where='dateFormatting'] Names the caller in the warning.
 * @returns {string}
 */
export function formatRunDateTime(dateISO, fallback = '', where = DEFAULT_CALLER_NAME) {
  if (!dateISO) return fallback;
  try {
    const d = new Date(dateISO);
    return `${d.toLocaleDateString(LOCALE, DAY_LONG_MONTH_YEAR_OPTS)} ${d.toLocaleTimeString(LOCALE, HOUR_MINUTE_OPTS)}`;
  } catch (err) {
    console.warn(`[${where}] date format failed:`, err);
    return fallback;
  }
}

/**
 * A run's time of day as "14:05". Same fallback contract as formatRunDate.
 *
 * @param {string|null|undefined} dateISO
 * @param {string} [fallback='']
 * @param {string} [where='dateFormatting']
 * @returns {string}
 */
export function formatRunTime(dateISO, fallback = '', where = DEFAULT_CALLER_NAME) {
  if (!dateISO) return fallback;
  try {
    return new Date(dateISO).toLocaleTimeString(LOCALE, HOUR_MINUTE_OPTS);
  } catch (err) {
    console.warn(`[${where}] time format failed:`, err);
    return fallback;
  }
}
