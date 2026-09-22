/**
 * Shared naming for the "file: N violations" bubble label, used by the risk
 * matrix bubbles and the galaxy view's keyboard items. The catalog has no
 * pluralisation, so a count of one takes its own key.
 */

/** The catalog key for a file's violation-count name, singular or plural. */
export function riskBubbleKey(violations) {
  return violations === 1 ? 'map.riskBubbleAriaOne' : 'map.riskBubbleAria';
}
