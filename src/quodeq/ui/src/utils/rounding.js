// Scores and deltas are shown with one decimal. One helper so the rounding
// rule (half away from zero, via Math.round) is the same everywhere.
const ONE_DECIMAL = 10; // 10^1: the factor for one decimal place

/**
 * Round to one decimal place, half away from zero (Math.round's own rule).
 * @param {number} n
 * @returns {number}
 */
export const roundOneDecimal = (n) => Math.round(n * ONE_DECIMAL) / ONE_DECIMAL;
