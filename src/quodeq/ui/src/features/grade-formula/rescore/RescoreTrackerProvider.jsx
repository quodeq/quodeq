import { RescoreTrackerContext } from './RescoreTrackerContext.js';
import { useRescoreOwner } from './useRescoreOwner.js';

/**
 * App-level owner of the grade-formula background rescore. Mounted once in
 * the app shell so the poll, and the score-cache invalidation when the pass
 * lands, keep going after the user leaves the Grade Formula page.
 */
export function RescoreTrackerProvider({ children }) {
  const value = useRescoreOwner();
  return <RescoreTrackerContext.Provider value={value}>{children}</RescoreTrackerContext.Provider>;
}
