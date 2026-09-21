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

  // Apply and reset differ only in which endpoint they call, what they log
  // and what they return; everything the server sends back is adopted the
  // same way. `run` performs the write and returns the formula payload.
  const submitFormula = useCallback(async (run, failureKey, logLabel) => {
    beginRequest();
    try {
      const d = await run();
      adoptServerFormula(d.current, d.isCustom);
      thresholdsStore.set(d.current.gradeThresholds);
      notePartialRescore(noticeFor(d));
      invalidateScoreQueries();
      requestPreview(d.current);
      return d;
    } catch (err) {
      console.warn(logLabel, err);
      failWith(t(failureKey));
      return null;
    } finally {
      endRequest();
    }
  }, [requestPreview, invalidateScoreQueries, thresholdsStore,
      beginRequest, endRequest, failWith, adoptServerFormula, notePartialRescore]);

  const apply = useCallback(async () => {
    const d = await submitFormula(
      () => saveGradeFormula(draft),
      'gradeFormula.applyFailed',
      '[useGradeFormula] apply failed:',
    );
    return d ? d.applied : null;
  }, [draft, submitFormula]);

  const resetToDefaults = useCallback(async () => {
    await submitFormula(
      resetGradeFormula,
      'gradeFormula.resetFailed',
      '[useGradeFormula] reset failed:',
    );
  }, [submitFormula]);

  return { draft, defaults, isCustom, isDirty, preview, busy, error, partialNotice, update, apply, resetToDefaults };
}
