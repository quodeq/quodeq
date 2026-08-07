// Catalog strings that need inline <code> spans carry them as `backticks`,
// the same convention translators already know from markdown. tRich() renders
// one such string into React nodes.
//
// Why not HTML in the catalog: t() returns a plain string and React escapes
// it, so "<code>x</code>" would render as literal angle brackets. Splitting a
// sentence into per-fragment keys instead would hand translators unassemblable
// pieces (see the impactBody keys in the standards sweep for that lesson).
// One key per sentence, with the code spans marked inline, keeps the sentence
// whole and the markup out of the translator's way.
import { t } from './index.js';

const CODE_SPAN = /`([^`]+)`/g;

export function tRich(key, vars) {
  const text = t(key, vars);
  const nodes = [];
  let last = 0;
  let match;
  CODE_SPAN.lastIndex = 0;
  while ((match = CODE_SPAN.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    nodes.push(<code key={match.index}>{match[1]}</code>);
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes.length === 0 ? text : <>{nodes}</>;
}
