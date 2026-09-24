import { useCallback } from 'react';
import { samePlaceholderScope } from '../api/queryKeys.js';

/** Query-key stand-in when no project is selected. */
const NO_PROJECT_KEY = '_none_';

/**
 * The project query key plus a `placeholderData` callback that reuses the
 * previous payload only within the same project+source subtree. An
 * unguarded `(prev) => prev` would show the PREVIOUS project's data after a
 * project switch (see samePlaceholderScope).
 */
export function useScopedPlaceholder(project, selectedSource) {
  const projectKey = project || NO_PROJECT_KEY;
  const keepInScope = useCallback(
    (prev, prevQuery) => (samePlaceholderScope(prevQuery, projectKey, selectedSource) ? prev : undefined),
    [projectKey, selectedSource],
  );
  return { projectKey, keepInScope };
}
