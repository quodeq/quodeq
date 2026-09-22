import { useEffect, useRef } from 'react';

// How long a pointer must stay down on an earlier segment before the
// sibling menu opens instead of navigating (mirrors browser back-button
// press-and-hold).
const HOLD_TO_OPEN_MS = 450;

/**
 * Press-and-hold on an earlier jump-bar segment opens its sibling menu (the
 * browser back-button convention); a released hold must then swallow the
 * click that follows the pointerup so it doesn't also navigate.
 */
export function useHoldToOpen(setOpenKey) {
  const holdTimer = useRef(null);
  const holdFired = useRef(false);
  useEffect(() => () => clearTimeout(holdTimer.current), []);

  const startHold = (key) => {
    holdFired.current = false;
    clearTimeout(holdTimer.current);
    holdTimer.current = setTimeout(() => {
      holdFired.current = true;
      setOpenKey(key);
    }, HOLD_TO_OPEN_MS);
  };
  const cancelHold = () => clearTimeout(holdTimer.current);
  const consumeHold = () => {
    const fired = holdFired.current;
    holdFired.current = false;
    return fired;
  };

  return { startHold, cancelHold, consumeHold };
}
