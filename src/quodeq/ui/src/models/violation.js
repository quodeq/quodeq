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
 * @property {number|string|null} endLine
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
 * @property {boolean}       provenanceDowngrade  true when the provenance gate (#639) de-escalated this from critical to major
 * @property {Object|null}   scopeDowngrade  {rule, from, to} when the scope gate capped this from major to minor per the declared trust model; null when not gated
 * @property {boolean}       carriedForward  true when replayed from the incremental cache rather than produced by the running scan
 */

import { fromFieldSpec } from './fieldSpec.js';

/**
 * Field table for {@link createViolation}: output key -> [raw spelling(s), default].
 *
 * Several fields arrive under two spellings. REST responses go through
 * `to_camel_dict`; raw JSON files and the SSE serializer emit the payload's
 * own snake_case, so both are tried. `practice_id` is the SSE spelling of
 * `principle`: missing it left every streamed finding with no principle.
 */
const VIOLATION_FIELDS = {
  file:                ['file', null],
  line:                ['line', null],
  endLine:             [['endLine', 'end_line'], null],
  severity:            ['severity', 'minor'],
  principle:           [['practiceId', 'practice_id', 'principle'], null],
  title:               ['title', null],
  reason:              [['reason', 'findings'], null],
  snippet:             [['snippet', 'code'], null],
  context:             ['context', null],
  scope:               ['scope', null],
  cwe:                 ['cwe', null],
  req:                 ['req', null],
  reqRefs:             [['reqRefs', 'req_refs'], () => []],
  dimension:           ['dimension', null],
  violationType:       [['violationType', 'violation_type'], null],
  provenanceDowngrade: [['provenanceDowngrade', 'provenance_downgrade'], false],
  scopeDowngrade:      [['scopeDowngrade', 'scope_downgrade'], null],
  carriedForward:      [['carriedForward', 'carried_forward'], false],
};

/**
 * Create a canonical Violation from a raw API object.
 *
 * @param {Object} raw
 * @returns {Violation}
 */
export function createViolation(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return fromFieldSpec(raw, VIOLATION_FIELDS);
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
