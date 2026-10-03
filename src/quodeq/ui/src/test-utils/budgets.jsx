/**
 * Frontend budget helpers: commits, fetches and cache entries.
 *
 * Performance tests assert counts, not timings, so they are deterministic:
 * how many times a page committed, how many requests a gesture fired, how
 * many entries a walk through History left in the cache. These three
 * helpers give those counts one shape so every budget test reads the same.
 *
 *   const page = countCommits(OverviewPage);
 *   render(<page.Counted {...props} />);          // page.commits() === 0
 *
 *   const fetches = countFetches(queryClient);     // requests, via the cache
 *   ...switch tabs...
 *   expect(fetches.count()).toBe(0);               // fetches.stop() when done
 *
 *   expect(cacheEntries(queryClient, ['projects', 'p1']).length).toBe(3);
 */
import { Profiler } from 'react';

// TanStack Query cache event names: a query "updated" by a "fetch" action is
// a request starting.
const QUERY_UPDATED_EVENT = 'updated';
const FETCH_ACTION = 'fetch';

/**
 * Wrap *Component* in a React Profiler and count its commits.
 *
 * `Counted` is a stable component type, so it can be rendered and
 * rerendered like the original. `reset()` zeroes the count after setup
 * renders, so a budget covers only the gesture under test.
 */
export function countCommits(Component, id = Component.displayName || Component.name || 'counted') {
  let commits = 0;
  function Counted(props) {
    return (
      <Profiler id={id} onRender={() => { commits += 1; }}>
        <Component {...props} />
      </Profiler>
    );
  }
  Counted.displayName = `Counted(${id})`;
  return { Counted, commits: () => commits, reset: () => { commits = 0; } };
}

function isFetchEvent(event) {
  return event.type === QUERY_UPDATED_EVENT && event.action?.type === FETCH_ACTION;
}

/**
 * Count requests as the query cache sees them: every query fetch start.
 *
 * There is no network layer in these tests (the API is a fake handed to
 * ApiProvider), so a fetch on the cache is the request. Counting here,
 * rather than on a spy per API method, covers every query regardless of
 * which fake method backs it, and stays valid when a fetch is deduplicated.
 *
 * `byKey()` groups the count by the query key's first segments, for the
 * assertion message when a budget is missed.
 */
export function countFetches(queryClient, { keyDepth = 2 } = {}) {
  const fetched = [];
  const stop = queryClient.getQueryCache().subscribe((event) => {
    if (isFetchEvent(event)) fetched.push(event.query.queryKey);
  });
  return {
    count: () => fetched.length,
    byKey: () => fetched.reduce((acc, key) => {
      const group = JSON.stringify(key.slice(0, keyDepth));
      acc[group] = (acc[group] || 0) + 1;
      return acc;
    }, {}),
    reset: () => { fetched.length = 0; },
    stop,
  };
}

/**
 * Cache entries whose key starts with *prefix* (deep-equal per segment).
 *
 * Returns the matching queries, so a test can count them or read the
 * segment it cares about (`q.queryKey.at(-1)`).
 */
export function cacheEntries(queryClient, prefix = []) {
  return queryClient.getQueryCache().getAll().filter((query) => (
    prefix.every((segment, i) => JSON.stringify(query.queryKey[i]) === JSON.stringify(segment))
  ));
}
