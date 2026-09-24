import { useEffect } from 'react';
import { focusables, restoreFocus } from '../../../utils/a11y.js';
import { KEY } from '../../../vocab/keyboard.js';

// Focus mechanics for the duel and dimension launcher popovers, the other
// half of useLauncherDismiss (which owns Escape and outside pointer/scroll).
const ARROW_STEP = { [KEY.ARROW_DOWN]: 1, [KEY.ARROW_UP]: -1 };
const MENUITEM_SELECTOR = '[role="menuitem"]';

/** Where focus lands on open: the first option, else anything focusable. */
function firstTarget(menu) {
  return menu.querySelector(MENUITEM_SELECTOR) || focusables(menu)[0] || null;
}

function moveFocus(menu, delta) {
  const items = focusables(menu);
  if (items.length === 0) return;
  const at = items.indexOf(document.activeElement);
  if (at === -1) {
    items[delta > 0 ? 0 : items.length - 1].focus();
    return;
  }
  items[(at + delta + items.length) % items.length].focus();
}

function launcherKeydown(menu, btn, close) {
  return (e) => {
    if (e.key === KEY.TAB) {
      e.preventDefault();
      close();
      restoreFocus(btn);
      return;
    }
    const delta = ARROW_STEP[e.key];
    if (delta === undefined) return;
    e.preventDefault();
    moveFocus(menu, delta);
  };
}

/**
 * Keeps keyboard focus inside a launcher popover for as long as it is open.
 *
 * Both menus are portaled to document.body, so they sit at the very end of
 * the document, disconnected from their trigger. Tab from the trigger would
 * walk past every remaining page control instead of entering the menu, which
 * leaves a keyboard-only user unable to reach the options at all. So the menu
 * takes focus itself when it opens, ArrowDown/ArrowUp walk it (wrapping at
 * both ends, over every focusable so the duel menu's unpin button is
 * reachable too), and Tab in either direction means "leave the menu": it
 * closes and hands focus back to the trigger, the one place from which
 * tabbing onward follows the visible order again.
 *
 * @param {boolean} open - drives the whole effect; only `open` is in the
 *   dependency list, so changing the refs or `close` mid-open is ignored.
 * @param {{current: HTMLElement|null}} btnRef - the trigger focus returns to.
 * @param {{current: HTMLElement|null}} menuRef - the portaled menu root.
 * @param {() => void} close - called when Tab asks to leave the menu.
 */
export function useLauncherFocus(open, btnRef, menuRef, close) {
  useEffect(() => {
    const menu = menuRef.current;
    if (!open || !menu) return undefined;
    const btn = btnRef.current;
    // The portal is already in the DOM by the time this effect runs, so the
    // first option can take focus straight away, no extra frame needed.
    const first = firstTarget(menu);
    if (first) first.focus();

    const onKeyDown = launcherKeydown(menu, btn, close);
    menu.addEventListener('keydown', onKeyDown);

    return () => {
      menu.removeEventListener('keydown', onKeyDown);
      // Closing must not drop focus on the floor. The menu is already
      // detached here, so focus that was on an option now reads as the body.
      // Anything else (a click on another control) keeps what it took.
      const active = document.activeElement;
      if (!active || active === document.body || menu.contains(active)) restoreFocus(btn);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // The open menu can re-render its own options away under the keyboard (the
  // duel menu drops the candidate it just pinned), which leaves focus on the
  // body with the menu still up and nothing to type at. Runs after the effect
  // above, so opening is unaffected; only a genuinely floored focus is caught.
  useEffect(() => {
    const menu = menuRef.current;
    if (!open || !menu) return;
    const active = document.activeElement;
    if (active && active !== document.body) return;
    const target = firstTarget(menu);
    if (target) target.focus();
  });
}
