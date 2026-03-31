/**
 * Violation / Finding model.
 *
 * Canonical representation of a code-quality finding.  Factory functions
 * accept raw JSON from any backend path (dashboard, dimension-eval, live
 * stream) and return a predictable shape so components never guess at
 * field names.
 *
 * @typedef {Object} ReqRef
 * @property {string} label
 * @property {string} url
 *
 * @typedef {Object} Violation
 * @property {string|null}   file
 * @property {number|string|null} line
 * @property {'critical'|'major'|'minor'} severity
 * @property {string|null}   principle
 * @property {string|null}   title
 * @property {string|null}   reason
 * @property {string|null}   snippet
 * @property {string|null}   context
 * @property {string|null}   scope
 * @property {number|string|null} cwe
 * @property {string|null}   req
 * @property {ReqRef[]}      reqRefs
 * @property {string|null}   dimension
 * @property {string|null}   violationType
 */

/**
 * Create a canonical Violation from a raw API object.
 *
 * Handles both camelCase (from to_camel_dict) and snake_case (from raw
 * JSON files) field names.
 *
 * @param {Object} raw
 * @returns {Violation}
 */
export function createViolation(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    file:          raw.file ?? null,
    line:          raw.line ?? null,
    severity:      raw.severity ?? 'minor',
    principle:     raw.principle ?? null,
    title:         raw.title ?? null,
    reason:        raw.reason ?? raw.findings ?? null,
    snippet:       raw.snippet ?? raw.code ?? null,
    context:       raw.context ?? null,
    scope:         raw.scope ?? null,
    cwe:           raw.cwe ?? null,
    req:           raw.req ?? null,
    reqRefs:       raw.reqRefs ?? raw.req_refs ?? [],
    dimension:     raw.dimension ?? null,
    violationType: raw.violationType ?? raw.violation_type ?? null,
  };
}

/**
 * Map an array of raw violation objects to canonical Violations.
 *
 * @param {Object[]} arr
 * @returns {Violation[]}
 */
export function createViolations(arr) {
  return (arr || []).map(createViolation);
}
