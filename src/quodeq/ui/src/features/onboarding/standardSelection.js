import { t } from '../../strings/index.js';

// The id of a bundled "default standard", when the server lists one. Today
// the list holds one entry per dimension, so the default is the whole visible
// set (the six quodeq dimensions unless the Standards tab narrowed it).
const DEFAULT_STANDARD_ID = 'default';

/**
 * The standards a new analysis runs against unless the user changes them:
 * the `default` standard if the list has one, else every visible standard.
 *
 * @param {Array<{ id: string }>} standards - the visible standards
 * @returns {string[]}
 */
export function defaultStandardIds(standards) {
  if (standards.some((s) => s.id === DEFAULT_STANDARD_ID)) return [DEFAULT_STANDARD_ID];
  return standards.map((s) => s.id);
}

function sameIds(a, b) {
  return a.length === b.length && a.every((id) => b.includes(id));
}

/**
 * How a pick reads on the analyze screen: one name and the dimensions it
 * covers. The whole default set reads as "quodeq default standard"; a
 * narrower pick names its standards.
 *
 * @param {Array<{ id: string, name: string, dimensions?: string[] }>} standards
 * @param {string[]} ids - the picked ids
 * @returns {{ name: string, dimensions: string[] }}
 */
export function describeStandards(standards, ids) {
  const picked = standards.filter((s) => ids.includes(s.id));
  if (picked.length === 1 && picked[0].dimensions) {
    return { name: picked[0].name, dimensions: picked[0].dimensions };
  }
  if (picked.length > 1 && sameIds(ids, defaultStandardIds(standards))) {
    return { name: t('onboarding.defaultStandard'), dimensions: picked.map((s) => s.id) };
  }
  return { name: picked.map((s) => s.name).join(', '), dimensions: [] };
}

/**
 * The pick after turning one standard on or off, in the list's order. The
 * last one cannot be turned off: a run needs at least one standard.
 *
 * @param {Array<{ id: string }>} standards
 * @param {string[]} ids
 * @param {string} id
 * @returns {string[]}
 */
export function toggledStandards(standards, ids, id) {
  const next = ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
  if (next.length === 0) return ids;
  return standards.map((s) => s.id).filter((x) => next.includes(x));
}
