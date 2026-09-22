/**
 * Which way a score delta points. The history rows show a delta three ways at
 * once (sign, colour class, arrow glyph); deriving all three from one call
 * keeps them from drifting apart the way three separate sign tests can.
 *
 * @param {number} delta - a finite delta; callers handle null/absent first.
 * @returns {'up'|'down'|'flat'} 'flat' also covers a delta of exactly zero.
 */
export function deltaDirection(delta) {
  if (delta > 0) return 'up';
  if (delta < 0) return 'down';
  return 'flat';
}
