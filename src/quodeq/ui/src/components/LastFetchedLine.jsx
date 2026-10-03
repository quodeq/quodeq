import { t } from '../strings/index.js';
import { relativeTime } from '../utils/relativeTime.js';

// The formatter lives in utils/relativeTime.js; re-exported so existing
// imports from this module keep working.
export { relativeTime };

export default function LastFetchedLine({ lastFetchedAt }) {
  if (!lastFetchedAt) return null;
  const rel = relativeTime(lastFetchedAt);
  if (rel === null) return null;
  return <p className="last-fetched-line">{t('common.lastUpdated')} {rel}.</p>;
}
