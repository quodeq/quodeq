/**
 * SevBadge — severity label rendered as a thin-outlined box using the theme's
 * `--color-sev-*` tokens.
 *
 * Formats:
 *   short  (default): CRIT, MAJ, MIN. Pair with `count` to get `CRIT 1`.
 *   long            : critical, major, minor (lowercase).
 *   count-abbr      : `1 crit`, `66 maj`, `161 min` — compact, count-first.
 *                     This is the layout used inside the VIOLATIONS stat
 *                     card on the overview.
 *
 * @param {object} props
 * @param {'critical'|'major'|'minor'} props.level
 * @param {'short'|'long'|'count-abbr'} [props.format]
 * @param {number} [props.count]
 */
const SHORT = { critical: 'CRIT', major: 'MAJ', minor: 'MIN' };
const LONG = { critical: 'critical', major: 'major', minor: 'minor' };
const ABBR = { critical: 'crit', major: 'maj', minor: 'min' };

export default function SevBadge({ level, format = 'short', count, onClick, ariaLabel }) {
  if (!level || !(level in SHORT)) return null;

  const baseClass = `term-sev-badge term-sev-badge--${level}`;

  if (format === 'count-abbr') {
    const className = `${baseClass} term-sev-badge--count-abbr${onClick ? ' term-sev-badge--clickable' : ''}`;
    const content = (
      <>
        {count != null ? count : ''}
        {count != null ? ' ' : ''}
        {ABBR[level]}
      </>
    );
    if (onClick) {
      return (
        <button
          type="button"
          className={className}
          onClick={(e) => { e.stopPropagation(); onClick(); }}
          aria-label={ariaLabel || `${level} severity`}
        >
          {content}
        </button>
      );
    }
    return <span className={className}>{content}</span>;
  }

  const text = format === 'short' ? SHORT[level] : LONG[level];
  const className = `${baseClass}${onClick ? ' term-sev-badge--clickable' : ''}`;
  const content = (
    <>
      {text}
      {count != null && <span className="term-sev-badge__count"> {count}</span>}
    </>
  );
  if (onClick) {
    return (
      <button
        type="button"
        className={className}
        onClick={(e) => { e.stopPropagation(); onClick(); }}
        aria-label={ariaLabel || `${level} severity`}
      >
        {content}
      </button>
    );
  }
  return <span className={className}>{content}</span>;
}
