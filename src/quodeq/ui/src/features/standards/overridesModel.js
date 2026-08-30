/**
 * Pure helpers for the per-project threshold-override draft in
 * StandardEditor. `overrides` is keyed by requirement id, each value a map
 * of paramName -> overridden value.
 */

/**
 * Apply one param change to an overrides draft. A null value clears that
 * param (and drops the requirement's entry entirely once it has none left).
 * structuredClone kept inside (strict move-only) so callers never share
 * references with the draft they started from.
 */
export function applyParamOverride(overrides, reqId, paramName, value) {
  const base = structuredClone(overrides);
  const reqOverrides = { ...(base[reqId] || {}) };
  if (value === null) delete reqOverrides[paramName];
  else reqOverrides[paramName] = value;
  if (Object.keys(reqOverrides).length === 0) delete base[reqId];
  else base[reqId] = reqOverrides;
  return base;
}

/** Count of requirements IN THIS STANDARD that carry an active override. */
export function countCustomizedRequirements(standard, overrides) {
  const reqIds = new Set(
    (standard?.principles || []).flatMap((p) => (p.requirements || []).map((r) => r.id)));
  return Object.keys(overrides).filter((id) => reqIds.has(id)).length;
}
