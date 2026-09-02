import { useCallback, useEffect } from 'react';
import { previewGradeFormula } from '../../../api/index.js';
import { clampFloors } from '../gradeFormulaRules.js';

const PREVIEW_DEBOUNCE_MS = 250;

/**
 * useGradeFormula.js's debounced preview request + the draft `update`
 * function that triggers it. Extracted verbatim -- the debounce and the
 * loadedRef-gated trigger effect's deps are unchanged.
 */
export function useGradePreview({ projectId, draft, setDraft, setPreview, debounceRef, loadedRef }) {
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
      const next = { ...prev, ...clampFloors(prev, patch) };
      requestPreview(next);
      return next;
    });
  }, [requestPreview]);

  return { requestPreview, update };
}
