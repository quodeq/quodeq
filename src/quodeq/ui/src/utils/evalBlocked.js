/**
 * Presentation for an action blocked while an evaluation is running.
 *
 * These buttons stay clickable — `aria-disabled` rather than `disabled` — so
 * the handler can explain the block instead of the click silently doing
 * nothing. The muted look comes from a class suffix and the reason from the
 * title, and every blocked action spells the same three attributes.
 */

// Appended to a blocked button's own classes; the styling lives in CSS.
const BLOCKED_CLASS = ' is-disabled';

/**
 * The class suffix a blocked button appends to its own classes.
 *
 * @param {boolean} isEvaluating
 * @returns {string} ' is-disabled' while blocked, '' otherwise.
 */
export function evalBlockedClass(isEvaluating) {
  return isEvaluating ? BLOCKED_CLASS : '';
}

/**
 * The aria/title props a blocked button carries.
 *
 * @param {boolean} isEvaluating
 * @param {string|undefined} blockedTitle Explains the block while it applies.
 * @param {string|undefined} [idleTitle] The button's normal title, if it has one.
 * @returns {{'aria-disabled': true|undefined, title: string|undefined}}
 */
export function evalBlockedProps(isEvaluating, blockedTitle, idleTitle) {
  return {
    'aria-disabled': isEvaluating || undefined,
    title: isEvaluating ? blockedTitle : idleTitle,
  };
}
