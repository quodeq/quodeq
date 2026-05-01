/**
 * FlagPill — CLI-style `--flag` toggle button.
 *
 * Rendered as `--name` or `--name (count)` when `count` is provided. When
 * `active`, the pill fills with the active accent color. Pass `tone` to apply
 * a severity accent (uses `--color-sev-<tone>-text` as the border/text color).
 *
 * @param {object} props
 * @param {string} props.flag             Flag name without leading dashes.
 * @param {boolean} [props.active]
 * @param {number}  [props.count]         Optional trailing count, e.g. `(2)`.
 * @param {string}  [props.tone]          One of "critical" | "major" | "minor".
 * @param {(e: any) => void} [props.onClick]
 * @param {string}  [props.title]
 */
export default function FlagPill({ flag, active = false, count, tone, onClick, title }) {
  let cls = 'term-flag-pill';
  if (active) cls += ' term-flag-pill--active';
  if (tone)   cls += ` term-flag-pill--${tone}`;
  return (
    <button type="button" className={cls} onClick={onClick} title={title} aria-pressed={active}>
      <span className="term-flag-pill__dashes" aria-hidden="true">--</span>
      <span className="term-flag-pill__name">{flag}</span>
      {count != null && <span className="term-flag-pill__count"> ({count})</span>}
    </button>
  );
}
