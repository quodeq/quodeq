/**
 * StatStrip — horizontal label/value strip.
 *
 * Use `<StatStrip>` as the container and `<Stat>` for each cell. The layout
 * is a responsive grid that auto-wraps on narrow widths.
 *
 * Example:
 *   <StatStrip>
 *     <Stat label="SCORE" value="9.0" hint="grade B · good" />
 *     <Stat label="VIOLATIONS" value="228" />
 *   </StatStrip>
 */
/**
 * Container variants:
 *   default — no chrome, children sit flush against the page.
 *   cards   — each `<Stat>` is its own bordered card (the overview layout).
 */
export function StatStrip({ children, cards = false }) {
  const classes = ['term-stat-strip'];
  if (cards) classes.push('term-stat-strip--cards');
  return <div className={classes.join(' ')}>{children}</div>;
}

/**
 * @param {object} props
 * @param {string} props.label
 * @param {React.ReactNode} props.value
 * @param {React.ReactNode} [props.hint]     Trailing muted text (e.g. "grade B · good").
 * @param {React.ReactNode} [props.trailing] Right-aligned accessory slot (badges, delta).
 * @param {string} [props.tone] One of "default" | "success" | "warning" | "critical".
 */
export function Stat({ label, value, hint, trailing, tone = 'default', onClick, ariaLabel }) {
  const className = `term-stat term-stat--${tone}${onClick ? ' term-stat--clickable' : ''}`;
  const labelValue = (
    <>
      <div className="term-stat__label">{label}</div>
      <div className="term-stat__value-row">
        <span className="term-stat__value">{value}</span>
        {trailing != null && <span className="term-stat__trailing">{trailing}</span>}
      </div>
    </>
  );
  const hintEl = hint != null ? <div className="term-stat__hint">{hint}</div> : null;
  if (onClick) {
    // The card itself stays a plain <div> so the hint — which may hold its own
    // interactive elements (e.g. clickable SevBadges) — sits beside the button
    // rather than inside it. Nesting a <button> in a <button> is invalid HTML,
    // breaks hydration, and is an accessibility trap. The label+value act as the
    // primary click target; severity badges remain independent siblings.
    return (
      <div className={className}>
        <button type="button" className="term-stat__hitbox" onClick={onClick} aria-label={ariaLabel || label}>
          {labelValue}
        </button>
        {hintEl}
      </div>
    );
  }
  return (
    <div className={className}>
      {labelValue}
      {hintEl}
    </div>
  );
}
