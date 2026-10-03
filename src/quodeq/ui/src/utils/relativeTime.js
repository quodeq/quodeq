import { t } from '../strings/index.js';
import { MS_PER_DAY, MS_PER_SECOND, SECONDS_PER_MINUTE, MINUTES_PER_HOUR, HOURS_PER_DAY } from './time.js';

const DAYS_PER_MONTH_APPROX = 30;
const MONTHS_PER_YEAR = 12;
// Below this many days, show "N days ago"; at/above it, switch to months.
const DAYS_AGO_THRESHOLD = 60;
// Below this many months, show "N months ago"; at/above it, switch to years.
const MONTHS_AGO_THRESHOLD = 24;
const MS_PER_MINUTE = SECONDS_PER_MINUTE * MS_PER_SECOND;

// Epoch ms for a timestamp given as epoch ms or an ISO string, else null.
// `new Date(null)` coerces to epoch 0 (NOT an Invalid Date), so a bare
// Number.isNaN guard would let a null/undefined timestamp compute a real
// ~56-year diff and render "57 years ago" instead of being treated as absent.
function toMs(when) {
  if (when == null) return null;
  const then = new Date(when).getTime();
  return Number.isNaN(then) ? null : then;
}

/**
 * Day-granular "N ago": today, yesterday, N days, months, years.
 * Every "N ago" display reuses this one formatter instead of growing a second.
 * @param {number|string|null|undefined} when - epoch ms or an ISO string
 * @returns {string|null} null when there is no valid timestamp
 */
export function relativeTime(when) {
  const then = toMs(when);
  if (then === null) return null;
  const days = Math.floor((Date.now() - then) / MS_PER_DAY);
  if (days <= 0) return t('common.today');
  if (days === 1) return t('common.yesterday');
  if (days < DAYS_AGO_THRESHOLD) return t('common.daysAgo', { days });
  const months = Math.floor(days / DAYS_PER_MONTH_APPROX);
  if (months < MONTHS_AGO_THRESHOLD) return t('common.monthsAgo', { months });
  return t('common.yearsAgo', { years: Math.floor(months / MONTHS_PER_YEAR) });
}

/**
 * Minute-granular within the last day ("just now", "2 min ago", "3 h ago"),
 * then the same as relativeTime. For things that change within a session,
 * such as when the team repository last synced.
 * @param {number|string|null|undefined} when - epoch ms or an ISO string
 * @returns {string|null}
 */
export function relativeTimeFine(when) {
  const then = toMs(when);
  if (then === null) return null;
  const minutes = Math.floor((Date.now() - then) / MS_PER_MINUTE);
  if (minutes < 1) return t('common.justNow');
  if (minutes < MINUTES_PER_HOUR) return t('common.minutesAgo', { minutes });
  const hours = Math.floor(minutes / MINUTES_PER_HOUR);
  if (hours < HOURS_PER_DAY) return t('common.hoursAgo', { hours });
  return relativeTime(then);
}
