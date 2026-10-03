/**
 * The TYPES tab's rows: the by-type rows of the run (byTypeModel) plus each
 * type's severity and the weight the draft formula gives it.
 */
import { buildTypeRows } from '../../violations/byTypeModel.js';
import { SEVERITY_ORDER } from '../../../vocab/severity.js';

const WEIGHT_DECIMALS = 1;

/**
 * The worst severity among the findings, or null when there are none.
 * @param {Array<{severity: string}>} violations
 * @returns {string|null}
 */
export function rowSeverity(violations) {
  const present = new Set((violations || []).map((v) => v.severity));
  return SEVERITY_ORDER.find((sev) => present.has(sev)) || null;
}

function weightOf(draft, severity) {
  const w = severity ? draft?.severityWeight?.[severity] : null;
  return typeof w === 'number' ? w.toFixed(WEIGHT_DECIMALS) : null;
}

/**
 * @param {{dimensions: Array, diffsByRun: Object, standardsByDim: Object, draft: object|null}} input
 * @returns {Array<Object>} byTypeModel rows with `severity` and `weight` (one decimal, or null)
 */
export function typesRows({ dimensions, diffsByRun, standardsByDim, draft }) {
  return buildTypeRows({ dimensions, diffsByRun, standardsByDim }).map((row) => {
    const severity = rowSeverity(row.violations);
    return { ...row, severity, weight: weightOf(draft, severity) };
  });
}
