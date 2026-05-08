function relativeTime(iso) {
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
