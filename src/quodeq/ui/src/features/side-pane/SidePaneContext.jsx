import { createContext, useContext } from 'react';

export const SidePaneContext = createContext(null);

export function useSidePane() {
  const ctx = useContext(SidePaneContext);
  if (ctx === null) {
    throw new Error('useSidePane must be used inside a <SidePaneProvider>');
  }
  return ctx;
}

/**
 * The side-pane context, or null when no <SidePaneProvider> is mounted. For
 * hooks that also run standalone (a pane rendered on its own in tests) and
 * degrade instead of throwing.
 */
export function useOptionalSidePane() {
  return useContext(SidePaneContext);
}
