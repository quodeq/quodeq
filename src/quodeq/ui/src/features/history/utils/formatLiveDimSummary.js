/**
 * Build the live dim-summary cell text for an in-progress History row.
 *
 * Inputs come from the SSE-fed TanStack Query cache:
 *   liveDims          : { [dim]: <evaluation/<dim>.json payload> }
 *   plannedDimensions : string[] from the latest status event's `dimensions`
 *
 * Empty `liveDims` → empty string (the caller renders the
 * "performing an evaluation..." placeholder in that case). Otherwise the
 * shape is `${done} / ${total} dims · ${abbrev1} ${score1}, ...`.
 *
 * If `plannedDimensions` is missing or empty (status not yet streamed),
 * the total falls back to the number of completed dims, so we never
 * render `1 / 0 dims`.
 */
import { abbrevDim } from './dimAbbrev.js';

export function formatLiveDimSummary(liveDims, plannedDimensions) {
  const entries = Object.values(liveDims || {}).filter((d) => d?.dimension);
  if (entries.length === 0) return '';
  const total = (plannedDimensions && plannedDimensions.length > 0)
    ? plannedDimensions.length
    : entries.length;
  const parts = entries.map((d) => {
    const raw = d.score ?? d.average_score;
    const score = parseFloat(raw);
    const label = abbrevDim(d.dimension);
    if (raw === undefined || raw === null || Number.isNaN(score)) return label;
    return `${label} ${score.toFixed(1)}`;
  });
  return `${entries.length} / ${total} dims · ${parts.join(', ')}`;
}
