/**
 * Pure option logic for Select. An entry of `options` is either an option,
 * `{ value, label, disabled? }`, or a named group of them, `{ group, options }`.
 */

/** Every option in display order, with groups opened up. */
export function flattenOptions(options) {
  return options.flatMap((entry) => entry.options || [entry]);
}

/** The next enabled index from `from` in direction `step`; `from` itself at the end of the list. */
export function stepEnabled(flat, from, step) {
  for (let i = from + step; i >= 0 && i < flat.length; i += step) {
    if (!flat[i].disabled) return i;
  }
  return from;
}

/** The first enabled index, or the last one when `step` is negative. */
export function edgeEnabled(flat, step) {
  return stepEnabled(flat, step > 0 ? -1 : flat.length, step);
}

/** The first enabled option whose label starts with `text`, or -1. */
export function matchTypeahead(flat, text) {
  const wanted = text.toLowerCase();
  return flat.findIndex((option) => !option.disabled && option.label.toLowerCase().startsWith(wanted));
}
