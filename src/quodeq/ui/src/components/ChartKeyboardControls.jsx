/**
 * ChartKeyboardControls — a keyboard- and screen-reader-accessible layer for
 * charts whose data points have no focusable DOM of their own (Recharts bars,
 * canvas visualizations).
 *
 * It renders one focusable <button> per data point, visually hidden until
 * keyboard-focused (then revealed at the top-left of the chart so sighted
 * keyboard users see where they are). Tab/Shift+Tab moves between points,
 * Enter/Space activates — reaching the SAME handler a mouse click does.
 *
 * Wrap the chart and this component in an element with `position: relative`
 * (e.g. `<div className="chart-with-kbd">`).
 *
 * Props:
 *   label  — accessible name for the control group (e.g. "Score history bars").
 *   items  — [{ key, text, onActivate }]. `text` is announced and shown on focus.
 */
export default function ChartKeyboardControls({ label, items }) {
  if (!items || items.length === 0) return null;
  return (
    <ul className="chart-kbd-controls" aria-label={label}>
      {items.map((it) => (
        <li key={it.key}>
          <button
            type="button"
            onClick={it.onActivate}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                it.onActivate();
              }
            }}
          >
            {it.text}
          </button>
        </li>
      ))}
    </ul>
  );
}
