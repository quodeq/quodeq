import { useState, useCallback, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { readVisibleStandardIds, writeVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { putStandardsVisibility } from '../../../api/standards.js';
import { projectKeys } from '../../../api/queryKeys.js';

function makePersist({ storage, projectId, queryClient }) {
  return (next) => {
    writeVisibleStandardIds(next, storage);
    // Fire-and-forget: the cache is already updated, so a failed write leaves
    // the UI correct for this session and re-syncs on the next hydrate.
    if (projectId) {
      putStandardsVisibility(projectId, next)
        // Compare caches this project's visibility set per query key —
        // invalidate AFTER the PUT lands so its refetch reads the new
        // server state instead of racing the write.
        .then(() => queryClient.invalidateQueries({ queryKey: projectKeys.standardsVisibility(projectId) }))
        .catch((err) => {
          console.warn('[useVisibleStandards] server sync failed:', err);
        });
    }
  };
}

// Every mutation is the same updater: compute the next list from the current
// one, persist it, and return it. `nextOf` returns the previous list itself
// to signal "nothing to do", which keeps React from re-rendering.
function makeVisibilityUpdater(setVisibleIds, persist, nextOf) {
  return (id) => {
    setVisibleIds((prev) => {
      const next = nextOf(prev, id);
      if (next === prev) return prev;
      persist(next);
      return next;
    });
  };
}

function makeToggle(setVisibleIds, persist) {
  return makeVisibilityUpdater(setVisibleIds, persist, (prev, id) => (
    prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
  ));
}

function makeAdd(setVisibleIds, persist) {
  return makeVisibilityUpdater(setVisibleIds, persist, (prev, id) => (
    prev.includes(id) ? prev : [...prev, id]
  ));
}

function makeRemove(setVisibleIds, persist) {
  return makeVisibilityUpdater(setVisibleIds, persist, (prev, id) => (
    prev.includes(id) ? prev.filter((x) => x !== id) : prev
  ));
}

/**
 * The set of standards the user has left visible, with add/remove/toggle.
 *
 * Membership tests are case-insensitive: the server lowercases stored ids but
 * imported ids are not charset-constrained, so a raw comparison would read a
 * visible standard as hidden. Changes are persisted and, with a `projectId`,
 * mirrored to that project's server-side visibility file.
 */
export function useVisibleStandards({ storage = localStorage, projectId = null } = {}) {
  const [visibleIds, setVisibleIds] = useState(() => readVisibleStandardIds(storage));
  const queryClient = useQueryClient();

  const persist = useCallback(makePersist({ storage, projectId, queryClient }), [storage, projectId, queryClient]);

  const toggle = useCallback(makeToggle(setVisibleIds, persist), [persist]);

  // Lowercase both sides: the server normalizes stored ids to lowercase,
  // but custom/imported standard ids aren't charset-constrained (e.g.
  // "OWASP-Top10"), so a raw comparison would read a visible standard as
  // hidden here while the assistant and dashboard correctly show it.
  const visibleSet = useMemo(
    () => new Set(visibleIds.map((id) => id.toLowerCase())), [visibleIds]);
  const isVisible = useCallback(
    (id) => visibleSet.has((id || '').toLowerCase()), [visibleSet]);

  const add = useCallback(makeAdd(setVisibleIds, persist), [persist]);

  const remove = useCallback(makeRemove(setVisibleIds, persist), [persist]);

  return { visibleIds, toggle, isVisible, add, remove };
}
