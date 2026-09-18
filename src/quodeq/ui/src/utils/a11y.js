/**
 * Keyboard and focus helpers shared by every interactive widget that is not a
 * native <button>: role="button" rows and cells, SVG hit targets, dialogs and
 * popover menus. One place for "Enter or Space activates" so no component
 * hand-rolls an Enter-only check again (U-ACC-3), and one tab trap for the
 * DOM-built dialogs and portaled menus.
 */
const ACTIVATION_KEYS = new Set(['Enter', ' ']);

// The tabindex clause does not look at `hidden`, `aria-disabled` or CSS
// visibility; a custom role="button" that is disabled by aria alone is
// still returned. The dialogs only ever append real <button>s, so this is
// a known limit, not a bug in their behaviour.
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

/** True for the keys that activate a control from the keyboard: Enter and Space. */
export function isActivationKey(e) {
  return ACTIVATION_KEYS.has(e.key);
}

/** Wrap a click handler so Enter and Space trigger it from the keyboard. */
export function activateOnKey(handler) {
  return (e) => {
    if (!isActivationKey(e)) return;
    e.preventDefault();
    handler(e);
  };
}

/** The tabbable descendants of `root`, in document order (see the selector's limits above). */
export function focusables(root) {
  return Array.from(root.querySelectorAll(FOCUSABLE_SELECTOR));
}

/** Keep Tab / Shift+Tab inside `root`; call from a keydown listener. */
export function trapTab(root, e) {
  if (e.key !== 'Tab') return;
  const items = focusables(root);
  if (items.length === 0) {
    e.preventDefault();
    return;
  }
  const first = items[0];
  const last = items[items.length - 1];
  const active = document.activeElement;
  if (!items.includes(active)) {
    // Focus is still outside root (an opener the caller never re-focused):
    // pull it in instead of letting the browser walk the page behind the
    // overlay.
    e.preventDefault();
    (e.shiftKey ? last : first).focus();
    return;
  }
  if (e.shiftKey && active === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && active === last) {
    e.preventDefault();
    first.focus();
  }
}

/** Return focus to the element that had it before a dialog opened. */
export function restoreFocus(el) {
  if (el && el.isConnected && typeof el.focus === 'function') el.focus();
}
