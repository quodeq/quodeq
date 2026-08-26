import { useEffect, useState } from 'react';
import { QMarkIcon } from './QMarkIcon.jsx';
import WarmupNotice from './WarmupNotice.jsx';
import { t } from '../strings/index.js';

const TIP_KEYS = [
  'loading.tips.warmup', 'loading.tips.incremental', 'loading.tips.dimensions',
  'loading.tips.dismiss', 'loading.tips.fixplans', 'loading.tips.standards',
  'loading.tips.ignore', 'loading.tips.history', 'loading.tips.compliance',
  'loading.tips.shared',
];
const TIPS_DELAY_MS = 300;
const TIPS_ROTATE_MS = 8000;
const LEAVE_MS = 400;

// Fisher-Yates copy shuffle: each launch walks the tips in a fresh order,
// still covering all of them before any repeat.
function shuffled(keys) {
  const out = [...keys];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function useRotatingTip(enabled) {
  const [order] = useState(() => shuffled(TIP_KEYS));
  const [idx, setIdx] = useState(-1);
  useEffect(() => {
    if (!enabled) return undefined;
    const start = setTimeout(() => setIdx(0), TIPS_DELAY_MS);
    return () => clearTimeout(start);
  }, [enabled]);
  const started = idx >= 0;
  useEffect(() => {
    if (!started) return undefined;
    const id = setInterval(() => setIdx((i) => (i + 1) % order.length), TIPS_ROTATE_MS);
    return () => clearInterval(id);
  }, [started, order.length]);
  return started ? order[idx] : null;
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
export default function LoadingScreen({ message, variant = 'fullscreen', tips = false, warmup = null, leaving = false }) {
  const tipKey = useRotatingTip(tips);
  const classes = ['loading-screen'];
  if (variant === 'inline') classes.push('loading-screen--inline');
  if (leaving) classes.push('loading-screen--leaving');
  return (
    <div className={classes.join(' ')} role="status" aria-live="polite">
      <QMarkIcon className="loading-logo" />
      {message && <p className="loading-message">{message}</p>}
      {tipKey && <p className="loading-tip">{t(tipKey)}</p>}
      <WarmupNotice warmup={warmup} />
    </div>
  );
}

/**
 * Fullscreen loader with a graceful exit. Stays mounted at a stable spot in
 * the tree; when `show` flips false it plays the fade-out (the leaving class)
 * and unmounts after it, instead of vanishing on the same frame the content
 * appears. Flipping `show` back mid-fade cancels the exit.
 */
export function FadingLoadingScreen({ show, ...props }) {
  const [mounted, setMounted] = useState(show);
  useEffect(() => {
    if (show) {
      setMounted(true);
      return undefined;
    }
    const id = setTimeout(() => setMounted(false), LEAVE_MS);
    return () => clearTimeout(id);
  }, [show]);
  if (!show && !mounted) return null;
  return <LoadingScreen {...props} leaving={!show} />;
}
