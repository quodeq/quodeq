import { useCallback, useEffect, useRef, useState } from 'react';
import { getGradeFormula } from '../../../api/index.js';
import { RESCORE_STATE } from '../../../vocab/rescoreState.js';
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
 * GET-on-mount effect.
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
  // The mount GET's payload when a background rescore is already running
  // (the user left mid-pass and came back), so the editor resumes polling.
  const [resumeFrom, setResumeFrom] = useState(null);
  const debounceRef = useRef(null);
  // State, not a ref: useGradePreview's trigger effect depends on it, and a
  // ref would never re-run that effect when the initial GET lands.
  const [loaded, setLoaded] = useState(false);

  const intents = useFormulaIntents({
    setSaved, setDraft, setIsCustom, setPreview, setBusy, setError, setPartialNotice,
  });
  const { adoptServerFormula } = intents;

  useEffect(() => {
    getGradeFormula()
      .then((d) => {
        setDefaults(d.defaults);
        adoptServerFormula(d.current, d.isCustom);
        if (d.rescore?.state === RESCORE_STATE.RUNNING) setResumeFrom(d);
        // A pass that failed while the editor was closed: say so on return.
        if (d.rescore?.state === RESCORE_STATE.ERROR) setError(t('gradeFormula.rescoreFailed'));
        setLoaded(true);
      })
      .catch(() => setError(t('gradeFormula.loadFailed')));
  }, [adoptServerFormula]);

  // Clear any pending debounced preview on unmount.
  useEffect(() => () => clearTimeout(debounceRef.current), []);

  return {
    saved, draft, isCustom, defaults, preview, busy, error, partialNotice,
    debounceRef, loaded, resumeFrom, ...intents,
  };
}
