import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useStandardsOverrides } from './useStandardsOverrides.js';
import { applyParamOverride, countCustomizedRequirements, decideSave } from '../overridesModel.js';
import { useAppState } from '../../../hooks/useAppState.js';
import { t } from '../../../strings/index.js';

function makeCommitSave({
  standard, editable, save, overridesDirty, overrides, saveOverrides, setDraftOverrides,
  onRescan, onSaved, setPendingImpact, setOverridesSaveError,
}) {
  return async (rescanDims = null) => {
    setPendingImpact(null);
    setOverridesSaveError(null);
    try {
      if (editable) await save();
      if (overridesDirty) {
        await saveOverrides(overrides);
        setDraftOverrides(null);
      }
      if (rescanDims?.length && onRescan) onRescan(rescanDims);
      if (onSaved) onSaved(standard?.id);
    } catch (err) {
      // Keep the draft so the user can retry; surface the error inline.
      setOverridesSaveError(err?.message || t('standards.saveOverridesFailed'));
    }
  };
}

/**
 * StandardEditor.jsx's threshold-overrides state and the save/impact-preview
 * flow (commitSave/handleSave), extracted verbatim.
 */
export function useStandardEditorOverrides({ standard, editable, save, onSaved, onRescan }) {
  const { selectedProject } = useAppState();
  const { overrides: savedOverrides, save: saveOverrides, preview: previewOverrides } = useStandardsOverrides(selectedProject);
  const [draftOverrides, setDraftOverrides] = useState(null);
  const [overridesSaveError, setOverridesSaveError] = useState(null);
  const [pendingImpact, setPendingImpact] = useState(null); // string[] of changed dimensions while the dialog is open
  const overrides = draftOverrides ?? savedOverrides;
  const overridesDirty = draftOverrides !== null;

  const savedOverridesRef = useRef(savedOverrides);
  useEffect(() => { savedOverridesRef.current = savedOverrides; }, [savedOverrides]);

  const handleChangeParam = useCallback((reqId, paramName, value) => {
    setDraftOverrides((prev) => applyParamOverride(prev ?? savedOverridesRef.current, reqId, paramName, value));
  }, []);

  const customizedCount = useMemo(
    () => countCustomizedRequirements(standard, overrides),
    [standard, overrides],
  );

  const commitSave = makeCommitSave({
    standard, editable, save, overridesDirty, overrides, saveOverrides, setDraftOverrides,
    onRescan, onSaved, setPendingImpact, setOverridesSaveError,
  });

  const handleSave = async () => {
    setOverridesSaveError(null);
    if (!overridesDirty) { await commitSave(); return; }
    try {
      const impact = await previewOverrides(overrides);
      const decision = decideSave({ overridesDirty, impact });
      if (decision === 'commit') { await commitSave(); return; }
      setPendingImpact(decision.confirm);
    } catch (err) {
      setOverridesSaveError(err?.message || t('standards.saveOverridesFailed'));
    }
  };

  return {
    selectedProject, overrides, overridesDirty, overridesSaveError, pendingImpact, setPendingImpact,
    customizedCount, handleChangeParam, commitSave, handleSave,
  };
}
