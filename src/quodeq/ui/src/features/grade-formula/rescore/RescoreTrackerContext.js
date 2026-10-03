import { createContext, useContext } from 'react';

export const RescoreTrackerContext = createContext(null);

export function useRescoreTracker() {
  const ctx = useContext(RescoreTrackerContext);
  if (!ctx) throw new Error('useRescoreTracker must be used inside <RescoreTrackerProvider>');
  return ctx;
}
