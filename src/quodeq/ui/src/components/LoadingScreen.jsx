import { useEffect, useState } from 'react';
import { QMarkIcon } from './QMarkIcon.jsx';
import { t } from '../strings/index.js';
import { renderRich } from '../strings/rich.jsx';

// One plain sentence each. The 8s rotation leaves reading time for about
// fifteen words; anything longer gets split into two tips. Each tip bolds the
// one thing worth catching at a glance (**...**) and marks file names and
// commands as `code`, so a skim still lands the point. A tip that opens with
// a question gets it on its own line: the reader decides from the question
// alone whether the rest applies to them.
const TIP_KEYS = [
  'loading.tips.warmup', 'loading.tips.incremental', 'loading.tips.cleanScan',
  'loading.tips.fixplans', 'loading.tips.dismiss', 'loading.tips.ignore',
  'loading.tips.assistant', 'loading.tips.riskMatrix', 'loading.tips.architecture',
  'loading.tips.compliance', 'loading.tips.stale', 'loading.tips.matrix',
  'loading.tips.duel', 'loading.tips.standards', 'loading.tips.customStandard',
  'loading.tips.prReview', 'loading.tips.ollama', 'loading.tips.monorepo',
  'loading.tips.shared',
];
const LEADING_QUESTION = /^([^?]+\?)\s+(.+)$/s;

function TipText({ text }) {
  const m = LEADING_QUESTION.exec(text);
  if (!m) return <p className="loading-tip__text">{renderRich(text)}</p>;
  return (
    <p className="loading-tip__text">
      <span className="loading-tip__question">{renderRich(m[1])}</span>
      {' '}
      {renderRich(m[2])}
    </p>
  );
}

const TIPS_DELAY_MS = 300;
const TIPS_ROTATE_MS = 8000;
// Each swap fades the old tip out, changes the text, then fades the new one in.
// Keep in step with the .loading-tip transition in base.css.
const TIP_FADE_MS = 700;
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
  const [fading, setFading] = useState(false);
  useEffect(() => {
    if (!enabled) return undefined;
    const start = setTimeout(() => setIdx(0), TIPS_DELAY_MS);
    return () => clearTimeout(start);
  }, [enabled]);
  const started = idx >= 0;
  useEffect(() => {
    if (!started) return undefined;
    let swap;
    const id = setInterval(() => {
      setFading(true);
      swap = setTimeout(() => {
        setIdx((i) => (i + 1) % order.length);
        setFading(false);
      }, TIP_FADE_MS);
    }, TIPS_ROTATE_MS);
    return () => { clearInterval(id); clearTimeout(swap); };
  }, [started, order.length]);
  return { tipKey: started ? order[idx] : null, fading };
}

// Non-default `variant` values (the default is 'fullscreen' -- see the
// LoadingScreen doc below).
const VARIANT_INLINE = 'inline';
const VARIANT_SHELL = 'shell';

/**
 * @param {{ message?: string, variant?: 'fullscreen'|'shell'|'inline', tips?: boolean }} props
 *
 * `message` labels what is being waited on. Worth passing whenever the wait
 * follows a user action that swapped the whole page's subject (e.g. switching
 * projects on the Overview), so the pulsing logo reads as "loading THAT" rather
 * than an unexplained blank.
 *
 * `variant` (default 'fullscreen'): 'fullscreen' is for cold start only (the
 * app-level Suspense fallback and any true first-load, before there's a page
 * frame to contain a loader). 'shell' is the boot overlay AppMain mounts in
 * the app shell's body row -- it covers sidebar, main column and side pane
 * (everything below the TopBar) and swallows clicks, so nothing underneath is
 * reachable while it's up. 'inline' is for everything mounted within an
 * already-rendered page -- it must not compete with, or hide behind, other
 * loaders or dimmed containers on the same route.
 *
 * `tips` rotates a help tip under the logo once a wait drags past a few
 * seconds.
 */
export default function LoadingScreen({ message, variant = 'fullscreen', tips = false, leaving = false }) {
  const { tipKey, fading } = useRotatingTip(tips);
  const classes = ['loading-screen'];
  if (variant === VARIANT_INLINE) classes.push('loading-screen--inline');
  if (variant === VARIANT_SHELL) classes.push('loading-screen--shell');
  // Known at mount, so the logo is lifted from the first frame and never
  // jumps when the first tip arrives.
  if (tips) classes.push('loading-screen--tips');
  if (leaving) classes.push('loading-screen--leaving');
  return (
    <div className={classes.join(' ')} role="status" aria-live="polite">
      <QMarkIcon className="loading-logo" />
      {message && <p className="loading-message">{message}</p>}
      {tipKey && (
        <div className={fading ? 'loading-tip loading-tip--fading' : 'loading-tip'}>
          <span className="loading-tip__label">{t('loading.tipLabel')}</span>
          <TipText text={t(tipKey)} />
        </div>
      )}
    </div>
  );
}

/**
 * Full-cover loader with a graceful exit. Stays mounted at a stable spot in
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
