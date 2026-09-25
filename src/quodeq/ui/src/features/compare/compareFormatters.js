// Number and label formatting shared by the compare feature's tables,
// cards and pickers. Kept in one place so every surface renders scores,
// counts and short labels the same way.
import { LOCALE } from '../../strings/index.js';
import { roundOneDecimal } from '../../utils/rounding.js';

// Per-project principle bar height, as a percent of the bar track: a near-
// zero score still renders a visible sliver instead of disappearing.
export const MIN_BAR_HEIGHT_PCT = 15;

// 0-10 score to bar height/width in percent (a full 10 score fills the bar).
// Shared by every principle/standing/duel bar so they all scale the same way.
export const SCORE_TO_PCT = 10;

// Scores are compared and shown at one decimal throughout the tab; rounding
// in one place keeps a computed gap agreeing with the numbers it was derived
// from.
export const roundScore1 = roundOneDecimal;

export const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
export const score1 = (s) => (s == null ? '—' : roundScore1(s).toFixed(1));
export const signed1 = (g) => (g == null ? '—' : (g > 0 ? `+${g.toFixed(1)}` : g.toFixed(1)));

// Short labels: the dimension tab bar and the matrix column headers speak
// the same shorthand, the label's first characters ("clean", "flexi",
// "maint"). When two labels share that prefix (the "independence from ..."
// principles) the matrix falls back to a readable stem built from the first
// and last significant words ("inde fra", "inde ui") so every header stays
// unique.
export const TAB_LABEL_CHARS = 5; // "clean", "flexi", "maint": the app's established shorthand
const STEM_HEAD_CHARS = 4; // "inde" of "independence"
const STEM_TAIL_CHARS = 3; // "fra" of "frameworks"
const STOPWORDS = new Set(['from', 'of', 'the', 'and', 'for']);

const significantWords = (label) => String(label || '')
  .trim()
  .split(/[\s-]+/)
  .filter((w) => w && !STOPWORDS.has(w));

export const prefixOf = (label) => String(label || '').trim().slice(0, TAB_LABEL_CHARS);

export function stemOf(label) {
  const words = significantWords(label);
  if (words.length <= 1) return (words[0] || '').slice(0, TAB_LABEL_CHARS);
  return `${words[0].slice(0, STEM_HEAD_CHARS)} ${words[words.length - 1].slice(0, STEM_TAIL_CHARS)}`;
}
