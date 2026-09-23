// Catalog strings that need inline <code> spans carry them as `backticks`,
// and emphasis as **double asterisks**, the same conventions translators
// already know from markdown. tRich() renders one such string into React
// nodes.
//
// Why not HTML in the catalog: t() returns a plain string and React escapes
// it, so "<code>x</code>" would render as literal angle brackets. Splitting a
// sentence into per-fragment keys instead would hand translators unassemblable
// pieces (see the impactBody keys in the standards sweep for that lesson).
// One key per sentence, with the code spans marked inline, keeps the sentence
// whole and the markup out of the translator's way.
import { t } from './index.js';

// Bold is tried first at each position, so a backtick inside **...** stays
// literal (e.g. **Ctrl+`**).
const RICH_SPAN = /\*\*([^*]+)\*\*|`([^`]+)`/g;

/** Render one already-translated string's inline markup into React nodes. */
export function renderRich(text) {
  const nodes = [];
  let last = 0;
  let match;
  RICH_SPAN.lastIndex = 0;
  while ((match = RICH_SPAN.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    nodes.push(match[1] !== undefined
      ? <strong key={match.index}>{match[1]}</strong>
      : <code key={match.index}>{match[2]}</code>);
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes.length === 0 ? text : <>{nodes}</>;
}

export function tRich(key, vars) {
  return renderRich(t(key, vars));
}
