/**
 * The catalog has no plural rules, so count-dependent copy is stored as a
 * singular key and a plural key.
 */

/**
 * Pick the catalog key for `count`: the singular key for exactly one, the
 * plural key otherwise.
 * @param {number} count
 * @param {string} oneKey Key for a count of one.
 * @param {string} manyKey Key for every other count.
 * @returns {string}
 */
export function pluralKey(count, oneKey, manyKey) {
  return count === 1 ? oneKey : manyKey;
}
