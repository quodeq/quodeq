import { useCallback, useEffect, useRef } from 'react';
import { previewGradeFormula } from '../../../api/index.js';
import { clampFloors } from '../gradeFormulaRules.js';

const PREVIEW_DEBOUNCE_MS = 250;

/**
 * The grade-formula editor's debounced preview request plus the draft
 * `update` that triggers it. Every keystroke restarts one shared timer, so
 * dragging a slider issues a single request once it settles.
 * @param {object} args
 * @param {string|null} args.projectId - no preview is requested without one.
 * @param {object|null} args.draft - the current draft formula.
 * @param {Function} args.updateDraft - applies a patch to the draft.
 * @param {Function} args.showPreview - receives the preview payload, or null
 *   when the request fails.
 * @param {{current: number|null}} args.debounceRef - the shared timer handle;
 *   owned by the caller so unmount can clear it.
 * @param {boolean} args.loaded - true once the initial GET has populated the
 *   draft; the first preview waits for it.
 * @returns {{requestPreview: Function, update: Function}}
 */
export function useGradePreview({ projectId, draft, updateDraft, showPreview, debounceRef, loaded }) {
  const requestPreview = useCallback((params) => {
    if (!projectId) return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      previewGradeFormula(projectId, params)
        .then(showPreview)
        .catch(() => showPreview(null));
    }, PREVIEW_DEBOUNCE_MS);
  }, [projectId]);

  // Fire the preview once both the draft (post-load) and the project are
  // known. update() handles every subsequent change, so this must NOT re-run
  // per draft edit: the draft is read through a ref so it stays out of the
  // dependency list while the effect still sees the current value.
  const draftRef = useRef(draft);
  draftRef.current = draft;
  useEffect(() => {
    if (loaded && draftRef.current && projectId) requestPreview(draftRef.current);
  }, [projectId, loaded, requestPreview]);

  const update = useCallback((patch) => {
    updateDraft((prev) => {
      const next = { ...prev, ...clampFloors(prev, patch) };
      requestPreview(next);
      return next;
    });
  }, [requestPreview]);

  return { requestPreview, update };
}
