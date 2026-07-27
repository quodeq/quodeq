import { QMarkIcon } from './QMarkIcon.jsx';

/**
 * @param {{ message?: string, variant?: 'fullscreen'|'inline' }} props
 *
 * `message` labels what is being waited on. Worth passing whenever the wait
 * follows a user action that swapped the whole page's subject (e.g. switching
 * projects on the Overview), so the pulsing logo reads as "loading THAT" rather
 * than an unexplained blank.
 *
 * `variant` (default 'fullscreen'): 'fullscreen' is for cold start only (the
 * app-level Suspense fallback and any true first-load, before there's a page
 * frame to contain a loader). 'inline' is for everything mounted within an
 * already-rendered page -- it must not compete with, or hide behind, other
 * loaders or dimmed containers on the same route.
 */
export default function LoadingScreen({ message, variant = 'fullscreen' }) {
  const className = variant === 'inline' ? 'loading-screen loading-screen--inline' : 'loading-screen';
  return (
    <div className={className} role="status" aria-live="polite">
      <QMarkIcon className="loading-logo" />
      {message && <p className="loading-message">{message}</p>}
    </div>
  );
}
