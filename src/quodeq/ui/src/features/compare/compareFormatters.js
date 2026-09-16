// Number formatting shared by the compare feature's tables, cards and
// pickers. Kept in one place so every surface renders scores and counts
// the same way.
import { LOCALE } from '../../strings/index.js';

export const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
export const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));
export const signed1 = (g) => (g > 0 ? `+${g.toFixed(1)}` : g.toFixed(1));
