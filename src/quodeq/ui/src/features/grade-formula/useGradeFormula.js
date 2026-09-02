import { useCallback } from 'react';
import { saveGradeFormula, resetGradeFormula } from '../../api/index.js';
import { defaultGradeThresholdsStore } from '../../utils/gradeThresholds.js';
import { useGradeFormulaState } from './hooks/useGradeFormulaState.js';
import { useGradePreview } from './hooks/useGradePreview.js';
import { t } from '../../strings/index.js';

// Singular and plural are separate whole sentences, not a stem plus an "s":
// the verb agreement moves too ("shows" vs "show"), and plenty of languages
// inflect more of the sentence than English does.
function noticeFor(d) {
  return d.failed > 0
    ? t(d.failed === 1 ? 'gradeFormula.partialRescoreOne' : 'gradeFormula.partialRescoreMany', { count: d.failed })
    : null;
}

/**
 * Grade-formula editor state: server params, dirty draft, debounced preview.
 * projectId: project used for the live preview (may be null).
 * thresholdsStore: grade-thresholds store apply/reset push the applied
 * boundaries into; defaults to the app-wide store, injectable so tests
 * don't leak grading state into the rest of the process.
 *
 * Split into hooks/useGradeFormulaState.js (server/draft/preview/busy/error
 * state + the initial load) and hooks/useGradePreview.js (the debounced
 * preview request + update()) -- this file composes the two and owns
 * apply/resetToDefaults.
 */
export default function useGradeFormula(projectId, thresholdsStore = defaultGradeThresholdsStore) {
  const {
    saved, setSaved, draft, setDraft, isCustom, setIsCustom, defaults,
    preview, setPreview, busy, setBusy, error, setError, partialNotice, setPartialNotice,
    debounceRef, loadedRef, invalidateScoreQueries,
  } = useGradeFormulaState();

  const isDirty = saved && draft && JSON.stringify(saved) !== JSON.stringify(draft);

  const { requestPreview, update } = useGradePreview({ projectId, draft, setDraft, setPreview, debounceRef, loadedRef });

  const apply = useCallback(async () => {
    setBusy(true); setError(null); setPartialNotice(null);
    try {
      const d = await saveGradeFormula(draft);
      setSaved(d.current); setDraft(d.current); setIsCustom(d.isCustom);
      thresholdsStore.set(d.current.gradeThresholds);
      setPartialNotice(noticeFor(d));
      invalidateScoreQueries();
      requestPreview(d.current);
      return d.applied;
    } catch {
      setError(t('gradeFormula.applyFailed'));
      return null;
    } finally {
      setBusy(false);
    }
  }, [draft, requestPreview, invalidateScoreQueries, thresholdsStore]);

  const resetToDefaults = useCallback(async () => {
    setBusy(true); setError(null); setPartialNotice(null);
    try {
      const d = await resetGradeFormula();
      setSaved(d.current); setDraft(d.current); setIsCustom(d.isCustom);
      thresholdsStore.set(d.current.gradeThresholds);
      setPartialNotice(noticeFor(d));
      invalidateScoreQueries();
      requestPreview(d.current);
    } catch {
      setError(t('gradeFormula.resetFailed'));
    } finally {
      setBusy(false);
    }
  }, [requestPreview, invalidateScoreQueries, thresholdsStore]);

  return { draft, defaults, isCustom, isDirty, preview, busy, error, partialNotice, update, apply, resetToDefaults };
}
