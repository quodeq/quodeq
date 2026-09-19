import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getGradeFormula } from '../../../api/index.js';
import { projectKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';

// The named writes the editor makes, so no consumer ever sees a raw setter.
// A server response (initial load, apply, reset) is authoritative for both
// the saved formula and the draft on screen, so the draft stops being dirty.
function useFormulaIntents({ setSaved, setDraft, setIsCustom, setPreview, setBusy, setError, setPartialNotice }) {
  const adoptServerFormula = useCallback((formula, custom) => {
    setSaved(formula);
    setDraft(formula);
    setIsCustom(custom);
  }, [setSaved, setDraft, setIsCustom]);

  // Start an apply/reset: busy on, last error and partial notice cleared.
  const beginRequest = useCallback(() => {
    setBusy(true);
    setError(null);
    setPartialNotice(null);
  }, [setBusy, setError, setPartialNotice]);

  const endRequest = useCallback(() => setBusy(false), [setBusy]);
  const failWith = useCallback((message) => setError(message), [setError]);
  const notePartialRescore = useCallback((notice) => setPartialNotice(notice), [setPartialNotice]);
  const updateDraft = useCallback((updater) => setDraft(updater), [setDraft]);
  const showPreview = useCallback((value) => setPreview(value), [setPreview]);

  return {
    adoptServerFormula, beginRequest, endRequest, failWith, notePartialRescore,
    updateDraft, showPreview,
  };
}

/**
 * useGradeFormula.js's server/draft/preview/busy/error state, the initial
 * GET-on-mount effect, and the score-query invalidation helper.
 *
 * The setters stay inside: callers get the named intents from
 * useFormulaIntents above, so the request choreography reads as what it
 * means rather than as a list of state writes.
 */
export function useGradeFormulaState() {
  const [saved, setSaved] = useState(null);     // params dict as saved server-side
  const [draft, setDraft] = useState(null);     // params dict being edited
  const [isCustom, setIsCustom] = useState(false);
  const [defaults, setDefaults] = useState(null);
  const [preview, setPreview] = useState(null); // {before, after} or null
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  // Set when an apply/reset rescored some runs but not all (a locked/corrupt
  // evaluation.db). Those runs keep the OLD formula's grades, so warn rather
  // than let the mismatch look like a bug.
  const [partialNotice, setPartialNotice] = useState(null);
  const debounceRef = useRef(null);
  const loadedRef = useRef(false); // true once the initial GET has populated draft
  const queryClient = useQueryClient();

  const intents = useFormulaIntents({
    setSaved, setDraft, setIsCustom, setPreview, setBusy, setError, setPartialNotice,
  });
  const { adoptServerFormula } = intents;

  // Applying or resetting the formula rewrites the SQL grade tables for every
  // run across every project (server-side apply_to_all_runs), so the cached
  // dashboard / accumulated-scores / project-card queries are now stale. Drop
  // the whole `project` subtree (scores + dashboard + runs) so they refetch.
  const invalidateScoreQueries = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: projectKeys.all() });
  }, [queryClient]);

  useEffect(() => {
    getGradeFormula()
      .then((d) => {
        setDefaults(d.defaults);
        adoptServerFormula(d.current, d.isCustom);
        loadedRef.current = true;
      })
      .catch(() => setError(t('gradeFormula.loadFailed')));
  }, [adoptServerFormula]);

  // Clear any pending debounced preview on unmount.
  useEffect(() => () => clearTimeout(debounceRef.current), []);

  return {
    saved, draft, isCustom, defaults, preview, busy, error, partialNotice,
    debounceRef, loadedRef, invalidateScoreQueries, ...intents,
  };
}
