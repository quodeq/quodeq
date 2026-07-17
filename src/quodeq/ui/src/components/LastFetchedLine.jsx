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
  const days = Math.floor(diffMs / 86400000);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 60) return `${days} days ago`;
  const months = Math.floor(days / 30);
  if (months < 24) return `${months} months ago`;
  return `${Math.floor(months / 12)} years ago`;
}

export default function LastFetchedLine({ lastFetchedAt }) {
  if (!lastFetchedAt) return null;
  const rel = relativeTime(lastFetchedAt);
  if (rel === null) return null;
  return <p className="last-fetched-line">Last updated {rel}.</p>;
}
