/**
 * ServerStatusDot — a minimal status light for the local server, shown in
 * the TopBar. A filled green dot when the server is reachable, a hollow red
 * ring when the connection is lost (the fill/ring shape carries the state so
 * it stays readable without relying on the red/green hue). The exact state
 * and address live in the hover tooltip / aria-label so the bar stays
 * uncluttered. Display-only: no click behavior.
 *
 * Renders nothing until the status is known (`connected == null`) rather than
 * flashing a misleading dot during the first health check.
 */
export default function ServerStatusDot({ connected, url }) {
  if (connected == null) return null;
  const host = url ? url.replace(/^https?:\/\//, '') : null;
  const label = connected
    ? (host ? `Server running · ${host}` : 'Server running')
    : 'Server offline';
  return (
    <span className="topbar-status-dot" role="img" aria-label={label} title={label}>
      <span
        className={`topbar-dot ${connected ? 'topbar-dot--ok' : 'topbar-dot--err'}`}
        aria-hidden="true"
      />
    </span>
  );
}
