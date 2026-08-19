import { useEffect, useState } from 'react';
import { QMarkIcon } from './QMarkIcon.jsx';
import WarmupNotice from './WarmupNotice.jsx';
import { t } from '../strings/index.js';

const TIP_KEYS = [
  'loading.tips.dimensions', 'loading.tips.history', 'loading.tips.dismiss',
  'loading.tips.standards', 'loading.tips.help', 'loading.tips.shared',
];
const TIPS_DELAY_MS = 5000;
const TIPS_ROTATE_MS = 8000;

function useRotatingTip(enabled) {
  const [idx, setIdx] = useState(-1);
  useEffect(() => {
    if (!enabled) return undefined;
    const start = setTimeout(() => setIdx(0), TIPS_DELAY_MS);
    return () => clearTimeout(start);
  }, [enabled]);
  const started = idx >= 0;
  useEffect(() => {
    if (!started) return undefined;
    const id = setInterval(() => setIdx((i) => (i + 1) % TIP_KEYS.length), TIPS_ROTATE_MS);
    return () => clearInterval(id);
  }, [started]);
  return started ? TIP_KEYS[idx] : null;
}

/**
 * @param {{ message?: string, variant?: 'fullscreen'|'inline', tips?: boolean, warmup?: object|null }} props
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
 *
 * `tips` rotates a help tip under the logo once a wait drags past a few
 * seconds. `warmup` renders the determinate preparing-data strip when a
 * post-update warm-up is running.
 */
export default function LoadingScreen({ message, variant = 'fullscreen', tips = false, warmup = null }) {
  const tipKey = useRotatingTip(tips);
  const className = variant === 'inline' ? 'loading-screen loading-screen--inline' : 'loading-screen';
  return (
    <div className={className} role="status" aria-live="polite">
      <QMarkIcon className="loading-logo" />
      {message && <p className="loading-message">{message}</p>}
      {tipKey && <p className="loading-tip">{t(tipKey)}</p>}
      <WarmupNotice warmup={warmup} />
    </div>
  );
}
