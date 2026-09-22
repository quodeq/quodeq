/**
 * Small helpers + the mirrored-bar component shared by CompareDuelView's
 * dimensions table and principles list.
 */
import { t } from '../../../strings/index.js';
import { score1 as fmtScore1 } from '../compareFormatters.js';

export { score1, signed1 } from '../compareFormatters.js';

const SCORE_TO_PCT = 10; // 0-10 score to bar width in percent

export function gapClass(gap) {
  if (gap == null || gap === 0) return 'compare-duel__gap--even';
  return gap > 0 ? 'compare-duel__gap--a' : 'compare-duel__gap--b';
}

/**
 * One side's score plus the side it belongs to. The bars and swatches beside
 * these numbers are decorative, so without the name a screen reader hears
 * two bare numbers per row with nothing tying either to a project (U-ACC-1).
 * The name is real text, not an aria-label: ARIA 1.2 prohibits aria-label on
 * a role-less span, and VoiceOver ignores it there.
 */
export function SideScore({ className, project, score }) {
  return (
    <span className={className}>
      <span aria-hidden="true">{fmtScore1(score)}</span>
      <span className="sr-only">
        {t('compare.sideScoreAria', { project, score: fmtScore1(score) })}
      </span>
    </span>
  );
}

/** Mirrored score bars growing from a shared centre line. */
export function DuelBars({ a, b }) {
  return (
    <span className="compare-duel__bars" aria-hidden="true">
      <span className="compare-duel__barLane compare-duel__barLane--a">
        {a != null && (
          <span className="compare-duel__bar compare-duel__bar--a" style={{ width: `${a * SCORE_TO_PCT}%` }} />
        )}
      </span>
      <span className="compare-duel__barLane compare-duel__barLane--b">
        {b != null && (
          <span className="compare-duel__bar compare-duel__bar--b" style={{ width: `${b * SCORE_TO_PCT}%` }} />
        )}
      </span>
    </span>
  );
}
