/**
 * Principle models — both dashboard (with violations) and graded (with scores).
 *
 * @typedef {import('./violation.js').Violation} Violation
 *
 * @typedef {Object} Principle
 * @property {string}      name
 * @property {string|null}  grade
 * @property {Violation[]}  violations
 * @property {Violation[]}  compliance
 * @property {string}       justification
 * @property {string[]}     recommendations
 * @property {Object|null}  metrics
 *
 * @typedef {Object} PrincipleGrade
 * @property {string}       principle
 * @property {string|null}  score
 * @property {string|null}  grade
 * @property {boolean}      isOverall
 */

import { createViolations } from './violation.js';

/**
 * Create a canonical Principle from a raw API object.
 *
 * @param {Object} raw
 * @returns {Principle}
 */
export function createPrinciple(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    name:            raw.name ?? '',
    grade:           raw.grade ?? null,
    score:           raw.score ?? null,
    violations:      createViolations(raw.violations),
    compliance:      createViolations(raw.compliance),
    justification:   raw.justification ?? '',
    recommendations: raw.recommendations ?? [],
    metrics:         raw.metrics ?? null,
    findings:        raw.findings ?? null,
  };
}

/**
 * Create a canonical PrincipleGrade.
 *
 * @param {Object} raw
 * @returns {PrincipleGrade}
 */
export function createPrincipleGrade(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    principle: raw.principle ?? '',
    score:     raw.score ?? null,
    grade:     raw.grade ?? null,
    isOverall: raw.isOverall ?? false,
  };
}
