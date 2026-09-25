import { t } from '../strings/index.js';
import { MS_PER_DAY } from '../utils/time.js';

const DAYS_PER_MONTH_APPROX = 30;
const MONTHS_PER_YEAR = 12;
// Below this many days, show "N days ago"; at/above it, switch to months.
const DAYS_AGO_THRESHOLD = 60;
// Below this many months, show "N months ago"; at/above it, switch to years.
const MONTHS_AGO_THRESHOLD = 24;

// Exported so other "N ago" displays (e.g. the Projects page's online-tab
// sync status and published-by lines) reuse this exact formatter instead of
// growing a second one.
export function relativeTime(iso) {
  // `new Date(null)` coerces to epoch 0 (NOT an Invalid Date), so a bare
  // Number.isNaN guard below lets a null/undefined timestamp compute a real
  // ~56-year diff and render "57 years ago" instead of being treated as
  // absent. Guard explicitly before the NaN check (which still catches
  // genuinely invalid strings like "not-a-date").
  if (iso == null) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const diffMs = Date.now() - then;
  const days = Math.floor(diffMs / MS_PER_DAY);
  if (days <= 0) return t('common.today');
  if (days === 1) return t('common.yesterday');
  if (days < DAYS_AGO_THRESHOLD) return t('common.daysAgo', { days });
  const months = Math.floor(days / DAYS_PER_MONTH_APPROX);
  if (months < MONTHS_AGO_THRESHOLD) return t('common.monthsAgo', { months });
  return t('common.yearsAgo', { years: Math.floor(months / MONTHS_PER_YEAR) });
}

export default function LastFetchedLine({ lastFetchedAt }) {
  if (!lastFetchedAt) return null;
  const rel = relativeTime(lastFetchedAt);
  if (rel === null) return null;
  return <p className="last-fetched-line">{t('common.lastUpdated')} {rel}.</p>;
}
