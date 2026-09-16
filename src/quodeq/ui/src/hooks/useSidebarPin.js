import { useState } from 'react';
import { MOBILE_BREAKPOINT_QUERY } from '../constants.js';

/**
 * Sidebar.jsx's pin state (controlled or internal) plus the toggle/nav
 * handlers, extracted verbatim.
 */
export function useSidebarPin({ controlledPinned, onPinChange, onNavTab }) {
  const [internalPinned, setInternalPinned] = useState(false);
  const isPinned = controlledPinned != null ? controlledPinned : internalPinned;
  const setPinned = (next) => {
    if (onPinChange) onPinChange(next);
    else setInternalPinned(next);
  };

  const handleTogglePin = () => setPinned(!isPinned);

  // Close the mobile drawer after navigating — otherwise the overlay stays
  // covering the just-navigated-to page.
  const handleNav = (id) => {
    onNavTab(id);
    if (typeof window !== 'undefined' && window.matchMedia(MOBILE_BREAKPOINT_QUERY).matches) {
      setPinned(false);
    }
  };

  return { isPinned, setPinned, handleTogglePin, handleNav };
}
