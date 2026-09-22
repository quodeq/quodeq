import { useCallback } from 'react';
import { consequenceOf, consequenceLevel } from '../compareModel.js';
import { storeScope } from '../compareScopeStorage.js';

/** Scope-selection actions: toggle one project, select all, select flagged. */
export function useCompareScopeActions({ scopeIds, setScopeIds, rows }) {
  const updateScope = useCallback((ids) => {
    setScopeIds(ids);
    storeScope(ids);
  }, [setScopeIds]);

  const toggleProject = useCallback((id) => {
    const current = scopeIds == null ? rows.map((r) => r.id) : scopeIds;
    const next = current.includes(id)
      ? current.filter((x) => x !== id)
      : current.concat([id]);
    updateScope(next.length === rows.length ? null : next);
  }, [scopeIds, rows, updateScope]);

  const selectFlagged = useCallback(() => {
    const flagged = rows
      .filter((r) => consequenceLevel(consequenceOf(r)) !== 'clear')
      .map((r) => r.id);
    updateScope(flagged.length ? flagged : null);
  }, [rows, updateScope]);

  const selectAll = useCallback(() => updateScope(null), [updateScope]);

  return { updateScope, toggleProject, selectFlagged, selectAll };
}
