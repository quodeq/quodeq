// Scores and deltas are shown with one decimal. One helper so the rounding
// rule (half up, toward +Infinity, via Math.round) is the same everywhere.
const ONE_DECIMAL = 10; // 10^1: the factor for one decimal place

/**
 * Round to one decimal place, half up (toward +Infinity), Math.round's rule.
 * @param {number} n
 * @returns {number}
 */
export const roundOneDecimal = (n) => Math.round(n * ONE_DECIMAL) / ONE_DECIMAL;

// A double sits exactly halfway between two tenths only at the quarters
// (x.25, x.75): n * 4 is exact, so an odd integer there marks the tie.
const QUARTERS = 4;

/**
 * Round to one decimal the way the server does (Python's round(n, 1)), for
 * a number the client recomputes beside one the server already sent. The
 * stored value is rounded, not its tenfold: 8.85 is 8.8499... in floating
 * point, so this gives 8.8 where roundOneDecimal gives 8.9 (8.85 * 10 is
 * exactly 88.5). An exact tie goes to the even tenth.
 * @param {number} n
 * @returns {number}
 */
export function roundOneDecimalLikeServer(n) {
  const quarters = n * QUARTERS;
  if (Number.isInteger(quarters) && quarters % 2 !== 0) {
    const down = Math.floor(n * ONE_DECIMAL);
    return (down % 2 === 0 ? down : down + 1) / ONE_DECIMAL;
  }
  return Number(n.toFixed(1));
}
