/**
 * IdentityStrip — the bordered fact row under a card title (repository ·
 * job id · scope · model · mode …). Purely presentational; both the setup
 * card and the running job card compose it from cells.
 */
export function IdentityStrip({ children }) {
  return <div className="eval-identity">{children}</div>;
}

/**
 * @param {object} props
 * @param {string} props.label      Uppercase cell label ("repository")
 * @param {boolean} [props.grow]    Cell absorbs the leftover width (ellipsizes)
 * @param {string} [props.title]    Tooltip for truncated values
 * @param {Function} [props.onClick] Makes the whole cell clickable (e.g.
 *   scope → folder browser, model → settings). The value renders as a
 *   button whose ::after stretches over the cell, so the full square is the
 *   hit target while accessories (the clear button) stay independent —
 *   same pattern as the clickable Stat cards.
 * @param {React.ReactNode} [props.trailing] Accessory rendered next to the
 *   value but outside it — needed when the value is a button and the
 *   accessory is one too (buttons must not nest)
 */
export function IdentityCell({ label, grow = false, title, onClick, trailing, children }) {
  const value = onClick ? (
    <button type="button" className="eval-identity__value eval-identity__value--action" onClick={onClick}>
      {children}
    </button>
  ) : (
    <span className="eval-identity__value">{children}</span>
  );
  const cellClass = `eval-identity__cell${grow ? ' eval-identity__cell--grow' : ''}${onClick ? ' eval-identity__cell--action' : ''}`;
  return (
    <div className={cellClass} title={title}>
      <span className="eval-identity__label">{label}</span>
      {trailing != null ? <span className="eval-identity__value-row">{value}{trailing}</span> : value}
    </div>
  );
}
