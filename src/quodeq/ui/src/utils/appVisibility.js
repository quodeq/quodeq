import { APP_VISIBILITY_EVENT } from '../constants.js';

/**
 * Whether the app window is hidden, and a subscription to that changing.
 *
 * Two signals feed it: `document.visibilityState`, which covers browser tabs,
 * and the native shell's APP_VISIBILITY_EVENT, which covers the desktop
 * window (pywebview leaves visibilityState on 'visible' when the window is
 * minimised, so the browser signal alone never reports hidden there).
 *
 * Callers use this to stop polling work the user cannot see. Everything here
 * is best effort: if the document or window APIs are unavailable the app is
 * treated as visible, which only costs the polls it would have skipped.
 */

const listeners = new Set();
let shellHidden = false;

// The document API surface this module touches, named so the checks below
// read as intent rather than as bare string comparisons.
const UNDEFINED = 'undefined';
const VISIBILITY_HIDDEN = 'hidden';

/**
 * Whether the browser itself reports the page as hidden. Covers tabs; the
 * desktop window never reports this (see the module doc).
 *
 * @returns {boolean}
 */
function documentHidden() {
  try {
    return typeof document !== UNDEFINED && document.visibilityState === VISIBILITY_HIDDEN;
  } catch (err) {
    console.warn('[appVisibility] document visibility unavailable:', err);
    return false;
  }
}

/**
 * Whether the app window is hidden right now.
 *
 * @returns {boolean}
 */
export function isHidden() {
  return shellHidden || documentHidden();
}

function notify() {
  for (const listener of [...listeners]) {
    try {
      listener();
    } catch (err) {
      console.warn('[appVisibility] listener failed:', err);
    }
  }
}

function onShellVisibility(event) {
  const next = !!event?.detail?.hidden;
  if (next === shellHidden) return;
  shellHidden = next;
  notify();
}

try {
  if (typeof document !== UNDEFINED) document.addEventListener('visibilitychange', notify);
  if (typeof window !== UNDEFINED) window.addEventListener(APP_VISIBILITY_EVENT, onShellVisibility);
} catch (err) {
  console.warn('[appVisibility] visibility events unavailable:', err);
}

/**
 * Call `listener` whenever the hidden state may have changed. Returns an
 * unsubscribe function.
 *
 * @param {() => void} listener
 * @returns {() => void}
 */
export function subscribeVisibility(listener) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/**
 * Clear the shell state and every subscriber. Test seam: the module-level
 * listeners outlive any one test file.
 */
export function resetAppVisibilityForTest() {
  shellHidden = false;
  listeners.clear();
}
