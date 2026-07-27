import { QMarkIcon } from './QMarkIcon.jsx';

/**
 * @param {{ message?: string }} props
 *
 * `message` labels what is being waited on. Worth passing whenever the wait
 * follows a user action that swapped the whole page's subject (e.g. switching
 * projects on the Overview), so the pulsing logo reads as "loading THAT" rather
 * than an unexplained blank.
 */
export default function LoadingScreen({ message }) {
  return (
    <div className="loading-screen" role="status" aria-live="polite">
      <QMarkIcon className="loading-logo" />
      {message && <p className="loading-message">{message}</p>}
    </div>
  );
}
