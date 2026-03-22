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
 * Create a canonical Dimension from a raw dashboard API object.
 *
 * @param {Object} raw
 * @returns {Dimension}
 */
export function createDimension(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    ...raw,
    violations:  createViolations(raw.violations),
    compliance:  createViolations(raw.compliance),
    principles:  (raw.principles || []).map(createPrinciple),
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
    violations:      createViolations(raw.violations),
    compliance:      createViolations(raw.compliance),
    principles:      (raw.principles || []).map(createPrinciple),
    principleGrades: (raw.principleGrades || []).map(createPrincipleGrade),
  };
}
