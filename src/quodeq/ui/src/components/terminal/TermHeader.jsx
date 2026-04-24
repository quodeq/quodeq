/**
 * TermHeader — page header with a `▶ name` prompt and optional sub line.
 * Renders in the active theme's accent color. Structural only; no layout
 * assumptions beyond "place at the top of a page".
 *
 * @param {object} props
 * @param {string} props.name   The label after the ▶ glyph.
 * @param {React.ReactNode} [props.sub]  Optional second line (e.g. stats, breadcrumb).
 */
export default function TermHeader({ name, sub }) {
  return (
    <header className="term-header">
      <div className="term-header__prompt">
        <span className="term-header__glyph" aria-hidden="true">▶</span>
        <span className="term-header__name">{name}</span>
      </div>
      {sub != null && <div className="term-header__sub">{sub}</div>}
    </header>
  );
}
