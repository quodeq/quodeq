/**
 * Shared positioning for the header launcher popovers (duel + dimension
 * triggers): a fixed-position menu anchored to its opener button, flipped
 * upward when the space below cannot fit it.
 */
export const LAUNCHER_MENU_MAX_H = 260; // keep in sync with the CSS max-height
const FLIP_GAP = 12; // breathing room wanted below the menu before it flips upward
const VIEWPORT_INSET = 8; // smallest gap kept between the menu and the viewport's left edge
const LAUNCHER_MENU_W = 228; // width reserved for .compare-dueltrigger__menu (min-width 200px plus padding, border and scrollbar) so it stays inside the right edge
const ANCHOR_GAP = 6; // gap between the opener button and the menu

export function launcherMenuPos(btn) {
  const r = btn?.getBoundingClientRect();
  if (!r) return null;
  const spaceBelow = window.innerHeight - r.bottom;
  const openUp = spaceBelow < LAUNCHER_MENU_MAX_H + FLIP_GAP && r.top > spaceBelow;
  return {
    left: Math.max(VIEWPORT_INSET, Math.min(r.left, window.innerWidth - LAUNCHER_MENU_W)),
    ...(openUp
      ? { bottom: window.innerHeight - r.top + ANCHOR_GAP }
      : { top: r.bottom + ANCHOR_GAP }),
  };
}
