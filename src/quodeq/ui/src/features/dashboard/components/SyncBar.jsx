const PERCENT_MAX = 100;

/**
 * The sync progress bar: determinate when the job reports a percent,
 * otherwise indeterminate (announced as busy, with no value). Used by the
 * sync strip and by a team card's pull.
 */
export function SyncBar({ percent = null, label }) {
  const known = typeof percent === 'number';
  const value = known ? Math.min(PERCENT_MAX, Math.max(0, Math.round(percent))) : null;
  return (
    <div
      className={`sync-strip__bar${known ? '' : ' sync-strip__bar--indeterminate'}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={PERCENT_MAX}
      aria-valuenow={known ? value : undefined}
      aria-busy={known ? undefined : true}
    >
      <span className="sync-strip__bar-fill" style={known ? { width: `${value}%` } : undefined} />
    </div>
  );
}
