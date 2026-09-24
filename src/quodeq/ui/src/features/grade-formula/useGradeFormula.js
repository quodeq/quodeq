import { useCallback } from 'react';
import { saveGradeFormula, resetGradeFormula } from '../../api/index.js';
import { defaultGradeThresholdsStore } from '../../utils/gradeThresholds.js';
import { RESCORE_STATE } from '../../vocab/rescoreState.js';
import { useGradeFormulaState } from './hooks/useGradeFormulaState.js';
import { useGradePreview } from './hooks/useGradePreview.js';
import { useRescoreProgress } from './hooks/useRescoreProgress.js';
import { t } from '../../strings/index.js';

// Singular and plural are separate whole sentences, not a stem plus an "s":
// the verb agreement moves too ("shows" vs "show"), and plenty of languages
// inflect more of the sentence than English does.
function noticeFor(rescore) {
  return rescore.failed > 0
    ? t(rescore.failed === 1 ? 'gradeFormula.partialRescoreOne' : 'gradeFormula.partialRescoreMany', { count: rescore.failed })
    : null;
}

// Once the server's pass for the latest apply has landed (or given up) while
// the editor is open: warn about runs that kept the old grades and refresh
// the preview, whose "before" side reads the rewritten grades. The app-level
// tracker drops the stale score caches whether or not the editor is open.
function settleRescore(payload, { failWith, notePartialRescore, requestPreview }) {
  const { rescore } = payload;
  if (rescore.state === RESCORE_STATE.ERROR) failWith(t('gradeFormula.rescoreFailed'));
  else notePartialRescore(noticeFor(rescore));
  requestPreview(payload.current);
}

/**
 * Grade-formula editor state: server params, dirty draft, debounced preview,
 * background-rescore progress.
 * projectId: project used for the live preview (may be null).
 * thresholdsStore: grade-thresholds store apply/reset push the applied
 * boundaries into; defaults to the app-wide store, injectable so tests
 * don't leak grading state into the rest of the process.
 *
 * Split into hooks/useGradeFormulaState.js (server/draft/preview/busy/error
 * state + the initial load), hooks/useGradePreview.js (the debounced preview
 * request + update()) and hooks/useRescoreProgress.js (the page's view of
 * the app-level rescore tracker in rescore/, which polls after an
 * apply/reset: the server answers with 202 and finishes in the background). This file composes them and owns apply/resetToDefaults.
 */
export default function useGradeFormula(projectId, thresholdsStore = defaultGradeThresholdsStore) {
  const {
    saved, draft, isCustom, defaults, preview, busy, error, partialNotice,
    debounceRef, loaded, resumeFrom,
    adoptServerFormula, beginRequest, endRequest, failWith, notePartialRescore,
    updateDraft, showPreview,
  } = useGradeFormulaState();

  const isDirty = saved && draft && JSON.stringify(saved) !== JSON.stringify(draft);

  const { requestPreview, update } = useGradePreview({ projectId, draft, updateDraft, showPreview, debounceRef, loaded });

  const { rescoreProgress, track } = useRescoreProgress(
    (payload) => settleRescore(payload, { failWith, notePartialRescore, requestPreview }),
    resumeFrom,
  );

  // Apply and reset differ only in which endpoint they call, what they log
  // and what they return; everything the server sends back is adopted the
  // same way. `run` performs the write and returns the formula payload.
  const submitFormula = useCallback(async (run, failureKey, logLabel) => {
    beginRequest();
    try {
      const d = await run();
      adoptServerFormula(d.current, d.isCustom);
      thresholdsStore.set(d.current.gradeThresholds);
      track(d);
      return d;
    } catch (err) {
      console.warn(logLabel, err);
      failWith(t(failureKey));
      return null;
    } finally {
      endRequest();
    }
  }, [track, thresholdsStore, beginRequest, endRequest, failWith, adoptServerFormula]);

  const apply = useCallback(async () => {
    const d = await submitFormula(
      () => saveGradeFormula(draft),
      'gradeFormula.applyFailed',
      '[useGradeFormula] apply failed:',
    );
    return d ? d.rescore : null;
  }, [draft, submitFormula]);

  const resetToDefaults = useCallback(async () => {
    await submitFormula(
      resetGradeFormula,
      'gradeFormula.resetFailed',
      '[useGradeFormula] reset failed:',
    );
  }, [submitFormula]);

  return {
    draft, defaults, isCustom, isDirty, preview, busy, error, partialNotice, rescoreProgress,
    update, apply, resetToDefaults,
  };
}
