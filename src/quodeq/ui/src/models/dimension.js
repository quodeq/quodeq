/**
 * Dimension result model — a scored dimension with its violations and principles.
 *
 * @typedef {import('./violation.js').Violation} Violation
 * @typedef {import('./principle.js').Principle} Principle
 * @typedef {import('./principle.js').PrincipleGrade} PrincipleGrade
 *
 * @typedef {Object} SeverityTally
 * @property {number} critical
 * @property {number} major
 * @property {number} minor
 *
 * @typedef {Object} DimensionTotals
 * @property {number}        violationCount
 * @property {number}        complianceCount
 * @property {SeverityTally} severity
 * @property {number|null}   [violationsPer100Files] - violations per 100 files
 *   read; null when nothing was read.
 *
 * @typedef {Object} Dimension
 * @property {string}        dimension
 * @property {string|null}   overallScore
 * @property {string|null}   previousScore
 * @property {string|null}   overallGrade
 * @property {string|number|null} trend
 * @property {Violation[]}   violations
 * @property {Violation[]}   compliance
 * @property {Principle[]}   principles
 * @property {DimensionTotals|null} totals
 * @property {string|null}   fromRunId
 * @property {string|null}   fromDateLabel
 * @property {string|null}   fromDateISO
 * @property {number|null}   [filesRead]         - files analyzed in this dim (older runs may not have it)
 * @property {number|null}   [sourceFileCount]   - total project source-file count (older runs may not have it)
 * @property {string|null}   [exitReason]        - per-dim or run-level exit signal,
 *   one of EXIT_REASON's values (see vocab/exitReason.js), or null/missing
 *   (legacy, treated as EXIT_REASON.DONE by the UI).
 * @property {number}        [dismissedCount]    - re-found violations hidden by the
 *   project-level dismissed filter (dashboard run view). Missing when zero.
 *
 * @typedef {Object} DimensionEval
 * @property {string}           dimension
 * @property {string}           runId
 * @property {string}           project
 * @property {PrincipleGrade[]} principleGrades
 * @property {Principle[]}      principles
 * @property {Violation[]}      violations
 * @property {Violation[]}      compliance
 * @property {boolean}          [partial]
 */

import { createViolations } from './violation.js';
import { createPrinciple, createPrincipleGrade } from './principle.js';

/**
 * A dimension's violation count for display: the totals count when present,
 * else the length of the violations list, else 0.
 *
 * @param {Dimension|Object} dim
 * @returns {number}
 */
export function dimensionViolationCount(dim) {
  if (typeof dim.totalViolations === 'number') return dim.totalViolations;
  if (Array.isArray(dim.violations)) return dim.violations.length;
  return 0;
}

/**
 * Create a canonical Dimension from a raw dashboard API object.
 *
 * @param {Object} raw
 * @returns {Dimension}
 */
export function createDimension(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return { ...raw, ...canonicalFindings(raw) };
}

// The violations/compliance/principles mapping both the dashboard Dimension
// and the DimensionEval apply, with an absent key coerced to an empty list.
function canonicalFindings(raw) {
  return {
    violations: createViolations(raw.violations),
    compliance: createViolations(raw.compliance),
    principles: (raw.principles || []).map(createPrinciple),
  };
}

/**
 * Create a Dimension from a slim scores payload (getRunScores/getCompareSummary
 * and their shared-repo mirrors), preserving the presence/absence of
 * violations/compliance/principles instead of coercing an absent key to `[]`.
 *
 * mergeRescoreIntoEval (explorerDataHooks.js) treats `violations != null` as a
 * tri-state: when the slim payload OMITS violations, prior violations are kept
 * as-is; when present (even `[]`), they're used to filter. createDimension's
 * unconditional `[]` coercion would collapse that distinction and silently
 * wipe every violation whenever a slim payload omits the key -- so this
 * factory only maps a field when it's actually an array.
 *
 * @param {Object} raw
 * @returns {Dimension}
 */
export function createSlimDimension(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    ...raw,
    violations: Array.isArray(raw.violations) ? createViolations(raw.violations) : raw.violations,
    compliance: Array.isArray(raw.compliance) ? createViolations(raw.compliance) : raw.compliance,
    principles: Array.isArray(raw.principles) ? raw.principles.map(createPrinciple) : raw.principles,
  };
}

/**
 * Create a canonical DimensionEval from the dimension-eval API response.
 *
 * @param {Object} raw
 * @returns {DimensionEval}
 */
export function createDimensionEval(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    ...raw,
    ...canonicalFindings(raw),
    principleGrades: (raw.principleGrades || []).map(createPrincipleGrade),
  };
}
