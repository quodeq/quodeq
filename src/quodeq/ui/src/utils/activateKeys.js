import { KEY } from '../vocab/keyboard.js';

/**
 * The keydown handler for an element that acts as a button (role="button"):
 * Enter and Space run `onActivate`. Keys from a nested control (an add,
 * remove or action button inside the row) belong to that control and are
 * left alone.
 *
 * @param {() => void} onActivate
 * @returns {(e: KeyboardEvent) => void}
 */
export function onActivateKeys(onActivate) {
  return (e) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === KEY.ENTER || e.key === ' ') {
      e.preventDefault();
      onActivate();
    }
  };
}
