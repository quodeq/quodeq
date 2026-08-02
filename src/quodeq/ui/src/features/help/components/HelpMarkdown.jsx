// Renders a help section from markdown.
//
// Help content is long-form documentation, so it lives as whole markdown
// documents per locale (src/features/help/content/<locale>/) rather than as
// hundreds of catalog keys: a translator needs to read a section as prose,
// not reassemble it from fragments. Everything else in the UI stays in
// en.json via t(); this is the one place where the unit of translation is a
// document.
//
// Four conventions let the prose carry the app's own furniture without
// dropping to MDX (which would mean a new build toolchain):
//
//   > **Title**          -> a Tip callout (blockquote whose first line is bold)
//   | Key | Value |      -> a KeyTable (GFM table)
//   ```figure            -> a registered figure component or image
//   `tag:critical`       -> a severity badge; `icon:eye` -> an inline icon
//
// The badge and icon labels come from the string catalog at render time, so
// no English leaks into the markdown for them.
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import HelpFigure from '../../../components/HelpFigure.jsx';
import GradeFormulaCurveFigure from './figures/GradeFormulaCurveFigure.jsx';
import ScoreGroupingFigure from './figures/ScoreGroupingFigure.jsx';
import gradeFormulaDark from '../../../assets/help/grade-formula.dark.webp';
import gradeFormulaLight from '../../../assets/help/grade-formula.light.webp';
import { t } from '../../../strings/index.js';
import { severityLabel } from '../../../strings/labels.js';

const FIGURES = { GradeFormulaCurveFigure, ScoreGroupingFigure };
const IMAGES = { gradeFormulaDark, gradeFormulaLight };

// Registry lookups must consider OWN keys only. A plain object inherits from
// Object.prototype, so `FIGURES['toString']` is a truthy function -- which
// means a mistyped `component: toString` in a markdown file would sail past a
// plain falsy check and be rendered as a React element, crashing the whole
// help page instead of skipping one figure. The unknown-name fallbacks below
// exist to degrade gracefully; without hasOwn they silently do not.
function pick(registry, key) {
  return Object.hasOwn(registry, key) ? registry[key] : undefined;
}

const ICONS = {
  eye: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ verticalAlign: 'middle', marginBottom: 2 }}>
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ),
};

function badgeLabel(kind) {
  return kind === 'compliance'
    ? t('explorer.compliantBadge')
    : severityLabel(kind).toUpperCase();
}

/** Parse a ```figure block body ("key: value" lines) into props. */
function parseFigure(body) {
  const props = {};
  for (const line of body.split('\n')) {
    const at = line.indexOf(':');
    if (at === -1) continue;
    const key = line.slice(0, at).trim();
    const value = line.slice(at + 1).trim();
    // `@name` refers to a bundled asset import, not a literal path.
    props[key] = value.startsWith('@') ? pick(IMAGES, value.slice(1)) : value;
  }
  return props;
}

function Figure({ body }) {
  const { component, caption, alt, srcDark, srcLight } = parseFigure(body);
  if (component && component !== 'image') {
    const Inner = pick(FIGURES, component);
    if (!Inner) return null;
    return <HelpFigure caption={caption}><Inner /></HelpFigure>;
  }
  return <HelpFigure caption={caption} alt={alt} srcDark={srcDark} srcLight={srcLight} />;
}

const COMPONENTS = {
  // A blockquote is the Tip callout. The leading bold run is its title.
  blockquote({ children }) {
    const nodes = Array.isArray(children) ? children.filter((c) => c !== '\n') : [children];
    const [head, ...rest] = nodes;
    const strong = head?.props?.children?.props?.type === 'strong'
      ? head.props.children
      : (Array.isArray(head?.props?.children) ? head.props.children[0] : head?.props?.children);
    const title = strong?.props?.children ?? null;
    return (
      <aside className="help-tip" role="note">
        {title && <div className="help-tip__title">{title}</div>}
        <div className="help-tip__body">{rest.length > 0 ? rest : head}</div>
      </aside>
    );
  },
  table({ children }) { return <div className="help-keytable" role="table">{children}</div>; },
  thead() { return null; },                       // the header row is scaffolding for GFM only
  tbody({ children }) { return children; },
  // Cell classes are positional (key, then value), so assign them here rather
  // than in `td`, which has no way to know which column it is.
  tr({ children }) {
    const cells = (Array.isArray(children) ? children : [children]).filter((c) => c !== '\n');
    return (
      <div className="help-keytable__row" role="row">
        {cells.map((cell, i) => (
          <div key={i} className={i === 0 ? 'help-keytable__k' : 'help-keytable__v'} role="cell">
            {cell?.props?.children}
          </div>
        ))}
      </div>
    );
  },
  code({ inline: isInline, className, children }) {
    const text = String(children ?? '');
    if (isInline !== false && !className) {
      if (text.startsWith('icon:')) return pick(ICONS, text.slice(5)) ?? null;
      if (text.startsWith('tag:')) {
        const kind = text.slice(4);
        return <span className={`severity-tag ${kind}`}>{badgeLabel(kind)}</span>;
      }
      return <code>{children}</code>;
    }
    if (className === 'language-figure') return <Figure body={text} />;
    if (className === 'language-text') return <pre className="help-pre">{text}</pre>;
    return <code className={className}>{children}</code>;
  },
  pre({ children }) { return children; },        // the code renderer emits its own wrapper
};

export default function HelpMarkdown({ source }) {
  return (
    <section className="help-section">
      <Markdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>{source}</Markdown>
    </section>
  );
}
