import { createContext, useContext } from 'react';

export const SidePaneContext = createContext(null);

export function useSidePane() {
  const ctx = useContext(SidePaneContext);
  if (ctx === null) {
    throw new Error('useSidePane must be used inside a <SidePaneProvider>');
  }
  return ctx;
}
