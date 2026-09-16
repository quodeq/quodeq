/**
 * Small helpers + the mirrored-bar component shared by CompareDuelView's
 * dimensions table and principles list.
 */
export { score1, signed1 } from '../compareFormatters.js';

export function gapClass(gap) {
  if (gap == null || gap === 0) return 'compare-duel__gap--even';
  return gap > 0 ? 'compare-duel__gap--a' : 'compare-duel__gap--b';
}

/** Mirrored score bars growing from a shared centre line. */
export function DuelBars({ a, b }) {
  return (
    <span className="compare-duel__bars" aria-hidden="true">
      <span className="compare-duel__barLane compare-duel__barLane--a">
        {a != null && (
          <span className="compare-duel__bar compare-duel__bar--a" style={{ width: `${a * 10}%` }} />
        )}
      </span>
      <span className="compare-duel__barLane compare-duel__barLane--b">
        {b != null && (
          <span className="compare-duel__bar compare-duel__bar--b" style={{ width: `${b * 10}%` }} />
        )}
      </span>
    </span>
  );
}
