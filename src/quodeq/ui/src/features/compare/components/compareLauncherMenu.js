/**
 * Shared positioning for the header launcher popovers (duel + dimension
 * triggers): a fixed-position menu anchored to its opener button, flipped
 * upward when the space below cannot fit it.
 */
export const LAUNCHER_MENU_MAX_H = 260; // keep in sync with the CSS max-height

export function launcherMenuPos(btn) {
  const r = btn?.getBoundingClientRect();
  if (!r) return null;
  const spaceBelow = window.innerHeight - r.bottom;
  const openUp = spaceBelow < LAUNCHER_MENU_MAX_H + 12 && r.top > spaceBelow;
  return {
    left: Math.max(8, Math.min(r.left, window.innerWidth - 228)),
    ...(openUp
      ? { bottom: window.innerHeight - r.top + 6 }
      : { top: r.bottom + 6 }),
  };
}
