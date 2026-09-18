/**
 * useEvaluationForm — form state + submit for the large (non-terminal)
 * EvaluationForm.
 *
 * Split out of EvaluationForm.jsx verbatim.
 */
import { useState, useEffect } from 'react';
import { usePluginDimensions } from './usePluginDimensions.js';
import { t } from '../../../strings/index.js';
import { buildEvaluationPayload } from '../components/evaluationFormHelpers.js';
import { CLEAN_PERSIST } from '../components/scanModes.js';

const NO_STANDARDS_MESSAGE = t('evaluate.noStandardsMessage');

function buildAndSubmit(onStart, formState) {
  const { repo, selectedDims, branch, scopePath, cleanScan, setRepo, setSelectedDims, setBranch, setScopePath, setCleanScan } = formState;
  const result = onStart(buildEvaluationPayload({ repo, selectedDims, branch, scopePath, cleanScan }));
  // Blocked start (another evaluation is running): keep the form and the
  // one-shot clean toggle intact so the user's retry submits the same thing.
  if (result === false) return;
  setRepo('');
  setSelectedDims(new Set());
  setBranch(null);
  setScopePath(null);
  if (cleanScan === CLEAN_PERSIST.ONCE) {
    Promise.resolve(result)
      .then(() => setCleanScan(CLEAN_PERSIST.OFF))
      .catch((err) => console.warn('[useEvaluationForm] start evaluation failed:', err));
  }
}

/**
 * The full Evaluate form: repo path, folder browser, branch and scope,
 * dimension selection, clean-scan mode and submit.
 *
 * Changing the repo clears the branch and scope, since neither is meaningful
 * against a different checkout. Submitting with standards available but none
 * selected reports through `onValidationFail` instead of starting.
 */
export function useEvaluationForm(onStart, onValidationFail) {
  const [repo, setRepo] = useState('');
  const { allDimensions, dimLoadError } = usePluginDimensions();
  const [selectedDims, setSelectedDims] = useState(new Set());
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);
  const [branch, setBranch] = useState(null);
  const [scopePath, setScopePath] = useState(null);
  const [cleanScan, setCleanScan] = useState(CLEAN_PERSIST.OFF);

  useEffect(() => { setScopePath(null); setBranch(null); }, [repo]);

  const toggleDim = (id) => setSelectedDims((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const selectAll = () => setSelectedDims(new Set(allDimensions.map((d) => d.id)));
  const clearAll = () => setSelectedDims(new Set());
  const handleSubmit = (e) => {
    e.preventDefault();
    if (allDimensions.length > 0 && selectedDims.size === 0) {
      onValidationFail?.(NO_STANDARDS_MESSAGE);
      return;
    }
    buildAndSubmit(onStart, { repo, selectedDims, branch, scopePath, cleanScan, setRepo, setSelectedDims, setBranch, setScopePath, setCleanScan });
  };
  const handleFolderSelect = (path) => { setRepo(path); setFolderBrowserOpen(false); };
  const handleRepoClear = () => { setRepo(''); setSelectedDims(new Set()); };

  return {
    repo, setRepo, allDimensions, selectedDims,
    folderBrowserOpen, setFolderBrowserOpen,
    toggleDim, selectAll, clearAll, handleSubmit,
    handleFolderSelect, handleRepoClear, dimLoadError,
    branch, setBranch, scopePath, setScopePath,
    cleanScan, setCleanScan,
  };
}
