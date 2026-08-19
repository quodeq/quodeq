import { t } from '../strings/index.js';

/** Determinate warm-up progress strip. Null unless a warm-up is running. */
export default function WarmupNotice({ warmup }) {
  if (!warmup?.active || !warmup.projectsTotal) return null;
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
