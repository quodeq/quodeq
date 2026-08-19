import { useEffect, useRef, useState } from 'react';
import { t } from '../strings/index.js';

const LINGER_MS = 1500;

/**
 * Determinate warm-up progress strip. Null unless a warm-up is running.
 * When the warm-up completes it holds a full bar with "Scores refreshed"
 * for a beat before hiding, instead of vanishing mid-progress.
 */
export default function WarmupNotice({ warmup }) {
  const active = !!(warmup?.active && warmup.projectsTotal);
  const [lingering, setLingering] = useState(false);
  const lastTotalRef = useRef(0);

  useEffect(() => {
    if (active) {
      lastTotalRef.current = warmup.projectsTotal;
      setLingering(false);
      return undefined;
    }
    if (!lastTotalRef.current) return undefined;
    setLingering(true);
    const id = setTimeout(() => {
      setLingering(false);
      lastTotalRef.current = 0;
    }, LINGER_MS);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  if (!active && !lingering) return null;

  if (!active) {
    return (
      <div className="warmup-notice" role="status">
        <div className="warmup-notice__bar">
          <div className="warmup-notice__fill" style={{ width: '100%' }} />
        </div>
        <p className="warmup-notice__label">{t('loading.refreshed')}</p>
      </div>
    );
  }

  const current = Math.min(warmup.projectsDone + 1, warmup.projectsTotal);
  const vars = { current, total: warmup.projectsTotal, name: warmup.currentProjectName };
  const label = warmup.currentProjectName
    ? t('loading.preparingNamed', vars)
    : t('loading.preparing', vars);
  const pct = Math.round((warmup.projectsDone / warmup.projectsTotal) * 100);
  return (
    <div className="warmup-notice" role="status">
      <div className="warmup-notice__bar">
        <div className="warmup-notice__fill" style={{ width: `${pct}%` }} />
      </div>
      <p className="warmup-notice__label">{label}</p>
    </div>
  );
}
