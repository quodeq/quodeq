/**
 * Map a numeric (or numeric-stringified, e.g. "9.1/10") dimension score to a
 * terminal-card grade word. Returns null for missing / non-numeric input so
 * the card can decide to omit the label.
 */
export function dimensionGradeLabel(score) {
  if (score === null || score === undefined || score === '') return null;
  const n = typeof score === 'number' ? score : parseFloat(score);
  if (Number.isNaN(n)) return null;
  if (n >= 9)   return 'EXEMPLARY';
  if (n >= 8)   return 'GOOD';
  if (n >= 7)   return 'FAIR';
  if (n >= 6)   return 'POOR';
  return 'CRITICAL';
}
