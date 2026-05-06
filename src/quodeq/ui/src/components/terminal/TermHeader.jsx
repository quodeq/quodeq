import HelpHint from '../HelpHint.jsx';

/**
 * TermHeader — page header with a `▶ name` prompt and optional sub line.
 * Renders in the active theme's accent color. Structural only; no layout
 * assumptions beyond "place at the top of a page".
 *
 * @param {object} props
 * @param {string} props.name   The label after the ▶ glyph.
 * @param {React.ReactNode} [props.sub]  Optional second line (e.g. stats, breadcrumb).
 * @param {string} [props.description]   Optional description shown via a click-to-open
 *   `?` popover after the name. Omit (or pass falsy) to hide the trigger.
 */
export default function TermHeader({ name, sub, description }) {
  const tip = typeof description === 'string' ? description.trim() : '';
  return (
    <header className="term-header">
      <div className="term-header__prompt">
        <span className="term-header__glyph" aria-hidden="true">▶</span>
        <span className="term-header__name">{name}</span>
        {tip && <HelpHint label={`About ${name}`}>{tip}</HelpHint>}
      </div>
      {sub != null && <div className="term-header__sub">{sub}</div>}
    </header>
  );
}
