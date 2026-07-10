/**
 * Resolves a requirement's display text by substituting param placeholders
 * with effective values (override if valid, otherwise default).
 *
 * Text without a `params` block is returned verbatim even if it contains
 * brace-delimited tokens — this matches backend resolution semantics exactly.
 */

const PLACEHOLDER = /\{([a-z_][a-z0-9_]*)\}/g;

function isValid(value, spec) {
  return (
    Number.isInteger(value) &&
    (spec.min == null || value >= spec.min) &&
    (spec.max == null || value <= spec.max)
  );
}

/**
 * Returns the effective value for a single param: the override if it is a
 * valid integer within [min, max], otherwise the spec default.
 *
 * @param {{ default: number, min?: number, max?: number }} spec
 * @param {*} override - Raw override value (may be absent / non-integer)
 * @returns {number}
 */
export function effectiveParamValue(spec, override) {
  return isValid(override, spec) ? override : spec.default;
}

/**
 * Resolve a requirement's text template against the given per-requirement
 * overrides map.
 *
 * @param {{ text?: string, params?: Object }} requirement
 * @param {Object|undefined} reqOverrides - e.g. `{ max_lines: 60 }`
 * @returns {string}
 */
export function resolveRequirementText(requirement, reqOverrides) {
  const params = requirement.params;
  if (!params) return requirement.text || '';
  return (requirement.text || '').replace(PLACEHOLDER, (match, name) => {
    const spec = params[name];
    if (!spec) return match;
    return String(effectiveParamValue(spec, reqOverrides?.[name]));
  });
}
