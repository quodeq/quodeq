/**
 * FlagPill — CLI-style `--flag` toggle button.
 *
 * Rendered as `--name` or `--name (count)` when `count` is provided. When
 * `active`, the pill fills with the active accent color.
 *
 * @param {object} props
 * @param {string} props.flag             Flag name without leading dashes.
 * @param {boolean} [props.active]
 * @param {number}  [props.count]         Optional trailing count, e.g. `(2)`.
 * @param {(e: any) => void} [props.onClick]
 * @param {string}  [props.title]
 */
export default function FlagPill({ flag, active = false, count, onClick, title }) {
  const cls = 'term-flag-pill' + (active ? ' term-flag-pill--active' : '');
  return (
    <button type="button" className={cls} onClick={onClick} title={title} aria-pressed={active}>
      <span className="term-flag-pill__dashes" aria-hidden="true">--</span>
      <span className="term-flag-pill__name">{flag}</span>
      {count != null && <span className="term-flag-pill__count"> ({count})</span>}
    </button>
  );
}
