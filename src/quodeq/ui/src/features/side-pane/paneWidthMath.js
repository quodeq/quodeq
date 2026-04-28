// Pure helpers for the resize divider — kept DOM-free so they're trivially testable.

export const MIN_RATIO = 0.30;
export const MAX_RATIO = 0.70;

export function clampSidePaneWidth(requestedPx, viewportPx) {
  const min = viewportPx * MIN_RATIO;
  const max = viewportPx * MAX_RATIO;
  const clamped = Math.min(Math.max(requestedPx, min), max);
  return Math.round(clamped);
}
