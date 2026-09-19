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
    saved, draft, isCustom, defaults, preview, busy, error, partialNotice,
    debounceRef, loadedRef, invalidateScoreQueries,
    adoptServerFormula, beginRequest, endRequest, failWith, notePartialRescore,
    updateDraft, showPreview,
  } = useGradeFormulaState();

  const isDirty = saved && draft && JSON.stringify(saved) !== JSON.stringify(draft);

  const { requestPreview, update } = useGradePreview({ projectId, draft, updateDraft, showPreview, debounceRef, loadedRef });

  const apply = useCallback(async () => {
    beginRequest();
    try {
      const d = await saveGradeFormula(draft);
      adoptServerFormula(d.current, d.isCustom);
      thresholdsStore.set(d.current.gradeThresholds);
      notePartialRescore(noticeFor(d));
      invalidateScoreQueries();
      requestPreview(d.current);
      return d.applied;
    } catch (err) {
      console.warn('[useGradeFormula] apply failed:', err);
      failWith(t('gradeFormula.applyFailed'));
      return null;
    } finally {
      endRequest();
    }
  }, [draft, requestPreview, invalidateScoreQueries, thresholdsStore,
      beginRequest, endRequest, failWith, adoptServerFormula, notePartialRescore]);

  const resetToDefaults = useCallback(async () => {
    beginRequest();
    try {
      const d = await resetGradeFormula();
      adoptServerFormula(d.current, d.isCustom);
      thresholdsStore.set(d.current.gradeThresholds);
      notePartialRescore(noticeFor(d));
      invalidateScoreQueries();
      requestPreview(d.current);
    } catch (err) {
      console.warn('[useGradeFormula] reset failed:', err);
      failWith(t('gradeFormula.resetFailed'));
    } finally {
      endRequest();
    }
  }, [requestPreview, invalidateScoreQueries, thresholdsStore,
      beginRequest, endRequest, failWith, adoptServerFormula, notePartialRescore]);

  return { draft, defaults, isCustom, isDirty, preview, busy, error, partialNotice, update, apply, resetToDefaults };
}
