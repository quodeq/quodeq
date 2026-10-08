/**
 * What each dimension card on the setup card says about the coming run, from
 * the pre-run estimates. No React, no network.
 */
import { t, LOCALE } from '../../strings/index.js';

// Files this dimension will analyze: every file on a clean scan, else the
// ones without a cached result.
function filesToAnalyze(est, isClean) {
  return isClean ? (est.total ?? 0) : (est.count ?? 0);
}

/**
 * Meta lines per dimension id: "N files to analyze" or "up to date"; null for
 * a dimension with no files. Only what the run will do: a cache percentage
 * beside a file count rounded 3,888 of 3,892 up to "100% analyzed".
 * @param {Object|null} estimates the /estimates payload
 * @param {boolean} isClean whether the scan is clean (re-reads every file)
 * @returns {Object<string, string[]|null>|null}
 */
export function buildDimMetas(estimates, isClean) {
  if (!estimates?.dimensions) return null;
  return Object.fromEntries(Object.entries(estimates.dimensions).map(([id, est]) => {
    if (!((est.total ?? 0) > 0)) return [id, null];
    const count = filesToAnalyze(est, isClean);
    if (count === 0) return [id, [t('evaluate.upToDate')]];
    return [id, [t('evaluate.filesToAnalyze', { count: count.toLocaleString(LOCALE) })]];
  }));
}

/**
 * Ids of dimensions with nothing to analyze in an incremental scan; empty on
 * a clean scan, which always has work.
 * @param {Object|null} estimates the /estimates payload
 * @param {boolean} isClean whether the scan is clean
 * @returns {Set<string>}
 */
export function buildUpToDateIds(estimates, isClean) {
  if (isClean || !estimates?.dimensions) return new Set();
  return new Set(Object.entries(estimates.dimensions)
    .filter(([, est]) => (est.total ?? 0) > 0 && (est.count ?? 0) === 0)
    .map(([id]) => id));
}
