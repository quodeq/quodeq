import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  getGradeFormula, saveGradeFormula, resetGradeFormula, previewGradeFormula,
} from '../../api/index.js';
import { projectKeys } from '../../api/queryKeys.js';
import { setGradeThresholds } from '../../utils/gradeThresholds.js';

const PREVIEW_DEBOUNCE_MS = 250;

/**
 * Grade-formula editor state: server params, dirty draft, debounced preview.
 * projectId: project used for the live preview (may be null).
 */
export default function useGradeFormula(projectId) {
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
      .catch(() => setError('Could not load grade formula'));
  }, []);

  // Clear any pending debounced preview on unmount.
  useEffect(() => () => clearTimeout(debounceRef.current), []);

  const isDirty = saved && draft && JSON.stringify(saved) !== JSON.stringify(draft);

  const requestPreview = useCallback((params) => {
    if (!projectId) return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      previewGradeFormula(projectId, params)
        .then(setPreview)
        .catch(() => setPreview(null));
    }, PREVIEW_DEBOUNCE_MS);
  }, [projectId]);

  // Fire the preview once both the draft (post-load) and the project are known.
  // update() handles every subsequent change, so this effect only needs to run
  // when the draft first loads (loadedRef flips) or the project changes.
  useEffect(() => {
    if (loadedRef.current && draft && projectId) requestPreview(draft);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, loadedRef.current]);

  const update = useCallback((patch) => {
    setDraft((prev) => {
      const next = { ...prev, ...patch };
      requestPreview(next);
      return next;
    });
  }, [requestPreview]);

  const noticeFor = (d) => (d.failed > 0
    ? `Applied, but ${d.failed} run${d.failed === 1 ? '' : 's'} could not be rescored and still show the old formula. Try applying again.`
    : null);

  const apply = useCallback(async () => {
    setBusy(true); setError(null); setPartialNotice(null);
    try {
      const d = await saveGradeFormula(draft);
      setSaved(d.current); setDraft(d.current); setIsCustom(d.isCustom);
      setGradeThresholds(d.current.gradeThresholds);
      setPartialNotice(noticeFor(d));
      invalidateScoreQueries();
      requestPreview(d.current);
      return d.applied;
    } catch {
      setError('Apply failed');
      return null;
    } finally {
      setBusy(false);
    }
  }, [draft, requestPreview, invalidateScoreQueries]);

  const resetToDefaults = useCallback(async () => {
    setBusy(true); setError(null); setPartialNotice(null);
    try {
      const d = await resetGradeFormula();
      setSaved(d.current); setDraft(d.current); setIsCustom(d.isCustom);
      setGradeThresholds(d.current.gradeThresholds);
      setPartialNotice(noticeFor(d));
      invalidateScoreQueries();
      requestPreview(d.current);
    } catch {
      setError('Reset failed');
    } finally {
      setBusy(false);
    }
  }, [requestPreview, invalidateScoreQueries]);

  return { draft, defaults, isCustom, isDirty, preview, busy, error, partialNotice, update, apply, resetToDefaults };
}
