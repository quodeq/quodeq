import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getGradeFormula } from '../../../api/index.js';
import { projectKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';

/**
 * useGradeFormula.js's server/draft/preview/busy/error state, the initial
 * GET-on-mount effect, and the score-query invalidation helper. Extracted
 * verbatim.
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
        setSaved(d.current); setDraft(d.current);
        setDefaults(d.defaults); setIsCustom(d.isCustom);
        loadedRef.current = true;
      })
      .catch(() => setError(t('gradeFormula.loadFailed')));
  }, []);

  // Clear any pending debounced preview on unmount.
  useEffect(() => () => clearTimeout(debounceRef.current), []);

  return {
    saved, setSaved, draft, setDraft, isCustom, setIsCustom, defaults, setDefaults,
    preview, setPreview, busy, setBusy, error, setError, partialNotice, setPartialNotice,
    debounceRef, loadedRef, invalidateScoreQueries,
  };
}
