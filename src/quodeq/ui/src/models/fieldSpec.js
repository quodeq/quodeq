/**
 * Field-spec reader shared by the model factories.
 *
 * Every factory does the same job: read a raw API object, try the spellings a
 * field can arrive under (camelCase from `to_camel_dict`, snake_case from raw
 * JSON files and SSE payloads) and fall back to a fixed default. Spelled out
 * longhand that is one `??` chain per field, and a factory with twenty fields
 * is a twenty-branch function that says nothing a table would not. Stating the
 * fields as data keeps the branching in one place, here.
 */

/**
 * First set value among `aliases` on `raw`, or the fallback when none is set.
 *
 * "Set" means what `??` means: `null` and `undefined` fall through, every other
 * value (`0`, `''`, `false`) is taken. A function fallback is called for its
 * value, so a field defaulting to a fresh array or object gets a new one per
 * call rather than a shared instance callers could mutate into each other.
 *
 * @param {Object} raw
 * @param {string[]} aliases   field spellings to try, in order
 * @param {*|function(): *} fallback
 * @returns {*}
 */
export function pickField(raw, aliases, fallback) {
  for (const alias of aliases) {
    const value = raw[alias];
    if (value !== undefined && value !== null) return value;
  }
  return typeof fallback === 'function' ? fallback() : fallback;
}

/**
 * Build a canonical object from a spec table.
 *
 * Each entry maps an output key to `[aliases, fallback]`, where `aliases` is
 * one field spelling or a list tried in order. The result keeps the table's
 * key order.
 *
 * @param {Object} raw
 * @param {Object<string, [string|string[], *]>} spec
 * @returns {Object}
 */
export function fromFieldSpec(raw, spec) {
  const out = {};
  for (const [key, [aliases, fallback]] of Object.entries(spec)) {
    out[key] = pickField(raw, Array.isArray(aliases) ? aliases : [aliases], fallback);
  }
  return out;
}
