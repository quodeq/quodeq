import { scoreColorClass } from '../../utils/formatters.js';

/**
 * One before -> after gauge. The label grade comes from the server's preview
 * response (`grade`), NOT from the client-side gradeThresholds store: during a
 * live preview the user may be dragging custom thresholds that haven't been
 * applied to the store yet, so recomputing client-side would disagree with what
 * Apply produces. Using the server grade keeps preview labels exactly equal to
 * the applied result (the project's core invariant).
 *
 * The color band (scoreColorClass) intentionally still reflects the APPLIED
 * thresholds from the store. That's acceptable: color is a coarse hint, the
 * authoritative label is the text next to it.
 */
function Gauge({ name, before, after, grade }) {
  const changed = before !== after && before != null && after != null;
  const insufficient = after == null || grade === 'Insufficient';
  return (
    <div className="gf-gauge">
      {changed ? <span className="gf-gauge-was">{before}</span> : null}
      <span className={`gf-gauge-now ${insufficient ? '' : scoreColorClass(after)}`}>
        {insufficient ? '-' : after}
      </span>
      <span className="gf-gauge-label">
        {name.toUpperCase()}
        {insufficient ? ' · INSUFF' : ` · ${(grade || '').toUpperCase()}`}
      </span>
    </div>
  );
}

/**
 * Bottom strip: OVERALL + per-dimension before->after gauges, left aligned.
 * preview: {before: {overall, dimensions}, after: {...}} or null.
 */
export default function PreviewStrip({ preview, emptyHint }) {
  if (!preview) {
    return (
      <div className="gf-preview">
        <span className="settings-description">{emptyHint}</span>
      </div>
    );
  }
  const beforeBy = Object.fromEntries(
    (preview.before?.dimensions || []).map((d) => [d.dimension, d.score]),
  );
  const dims = preview.after?.dimensions || [];
  return (
    <div className="gf-preview">
      <div className="gf-gauges">
        <Gauge
          name="overall"
          before={preview.before?.overall?.score}
          after={preview.after?.overall?.score}
          grade={preview.after?.overall?.grade}
        />
        {dims.map((d) => (
          <Gauge
            key={d.dimension}
            name={d.dimension}
            before={beforeBy[d.dimension]}
            after={d.score}
            grade={d.grade}
          />
        ))}
      </div>
    </div>
  );
}
