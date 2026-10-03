// Mirror of src/quodeq/core/types/project_source.py:ProjectSource. Where a
// selected project's data lives: this machine's evaluations or the shared
// repository mirror. Wire value and the cache-key segment (api/queryKeys.js).
export const PROJECT_SOURCE = Object.freeze({ LOCAL: 'local', SHARED: 'shared' });
// What every source-taking factory and hook falls back to when none is passed.
export const DEFAULT_PROJECT_SOURCE = PROJECT_SOURCE.LOCAL;
