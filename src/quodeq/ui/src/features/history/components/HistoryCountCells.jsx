/**
 * The evaluations table's numeric cells: a delta with sign and colour, and
 * a plain count. Both degrade to the muted placeholder when there is no
 * number.
 */
import { deltaDirection } from '../utils/deltaDirection.js';

const DELTA_SIGN = { up: '+', down: '-', flat: '' };
const DELTA_CLASS = {
  up: 'history-delta history-delta--up',
  down: 'history-delta history-delta--down',
  flat: 'history-delta',
};
// Lower is better for majors and open types: a drop colours as "up".
const INVERTED = { up: 'down', down: 'up', flat: 'flat' };

// Drop trailing .0 so integers render as "9" and zeros as "0" — matches mock.
const TRAILING_ZERO_SUFFIX_LENGTH = 2; // ".0"

export function trimTrailingZero(n) {
  const fixed = n.toFixed(1);
  return fixed.endsWith('.0') ? fixed.slice(0, -TRAILING_ZERO_SUFFIX_LENGTH) : fixed;
}

export function DeltaText({ delta, invert = false }) {
  if (delta == null) return <span className="history-delta history-delta--muted">—</span>;
  const raw = deltaDirection(delta);
  const direction = invert ? INVERTED[raw] : raw;
  const abs = Math.abs(delta);
  return <span className={DELTA_CLASS[direction]}>{DELTA_SIGN[raw]}{trimTrailingZero(abs)}</span>;
}

export function CountCell({ value }) {
  if (value == null) return <span className="history-row__muted">—</span>;
  return <span className="history-row__count">{value}</span>;
}
