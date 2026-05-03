/**
 * Top-of-wizard progress indicator. Renders nothing when total=0 (e.g. on the
 * Welcome step or during transient launching state).
 */
export default function StepProgress({ current, total }) {
  if (!total || total <= 0) return null;
  const safe = Math.max(1, Math.min(current, total));
  const pct = (safe / total) * 100;
  return (
    <div className="step-progress" role="progressbar" aria-valuemin={1} aria-valuemax={total} aria-valuenow={safe}>
      <div className="step-progress__label">Step {safe} of {total}</div>
      <div className="step-progress__track">
        <div className="step-progress__fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
