import { useState, useEffect, useCallback } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import {
  addPrincipleToStandard, removePrincipleFromStandard,
  addRequirementToStandard, removeRequirementFromStandard, updateStandardField,
} from '../standardTreeModel.js';
import { STANDARD_TYPES } from './useStandards.js';
import { t } from '../../../strings/index.js';

// addPrinciple/addRequirement call setSelectedNode from INSIDE the
// setStandard updater (a pre-existing bug — fires twice under StrictMode);
// removePrinciple/removeRequirement call it OUTSIDE, right after setStandard,
// since their target never depends on `prev`. Both placements are preserved
// exactly as they were before this move — not purity-fixed here; see
// standardTreeModel.js's docstring.
function useTreeMutations(setStandard, setDirty, setSelectedNode) {
  const addPrinciple = useCallback(() => {
    setStandard((prev) => {
      const { standard, selectedNode } = addPrincipleToStandard(prev);
      setSelectedNode(selectedNode);
      return standard;
    });
    setDirty(true);
  }, [setStandard, setDirty]);

  const removePrinciple = useCallback((index) => {
    // setSelectedNode is called OUTSIDE the updater here, matching the
    // original exactly (its value never depended on `prev`, so it was never
    // inside the updater to begin with — don't relocate it).
    setStandard((prev) => removePrincipleFromStandard(prev, index).standard);
    setDirty(true);
    setSelectedNode({ type: 'root' });
  }, [setStandard, setDirty]);

  const addRequirement = useCallback((principleIndex) => {
    setStandard((prev) => {
      const { standard, selectedNode } = addRequirementToStandard(prev, principleIndex);
      setSelectedNode(selectedNode);
      return standard;
    });
    setDirty(true);
  }, [setStandard, setDirty]);

  const removeRequirement = useCallback((principleIndex, reqIndex) => {
    // setSelectedNode is called OUTSIDE the updater here too, matching the
    // original: its value only depends on the passed-in principleIndex, so
    // it never needed to read `prev` inside the updater.
    setStandard((prev) => removeRequirementFromStandard(prev, principleIndex, reqIndex).standard);
    setDirty(true);
    setSelectedNode({ type: 'principle', index: principleIndex });
  }, [setStandard, setDirty]);

  return { addPrinciple, removePrinciple, addRequirement, removeRequirement };
}

function useStandardMutations(standard, setStandard, setDirty, standardId, isNew, { createStandard, updateStandard }) {
  const [selectedNode, setSelectedNode] = useState(null);

  // updateStandardField deep-clones so React detects state changes via
  // referential inequality across the entire nested standard tree (principles
  // -> requirements). The tree is small (typically <50 nodes), so JSON
  // round-trip cost is negligible.
  const updateField = useCallback((path, value) => {
    setStandard((prev) => updateStandardField(prev, path, value));
    setDirty(true);
  }, [setStandard, setDirty]);

  const tree = useTreeMutations(setStandard, setDirty, setSelectedNode);

  const save = useCallback(async () => {
    if (!standard) return;
    if (!standard.id) return { error: t('standards.idRequired') };
    if (!standard.name) return { error: t('standards.nameRequired') };
    try {
      if (isNew) { await createStandard(standard); } else { await updateStandard(standard.id, standard); }
      setDirty(false);
      return { error: null };
    } catch (err) { return { error: err.message }; }
  }, [standard, isNew, setDirty]);

  return { selectedNode, setSelectedNode, updateField, ...tree, save };
}

export function useStandardDetail(standardId, isNew) {
  const { getStandard, createStandard, updateStandard } = useApi();
  const [standard, setStandard] = useState(null);
  const [loading, setLoading] = useState(!isNew);
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);

  const mutations = useStandardMutations(standard, setStandard, setDirty, standardId, isNew, { createStandard, updateStandard });

  useEffect(() => {
    if (isNew) {
      setStandard({ id: '', name: '', description: '', weight: 1.0, source: '', type: STANDARD_TYPES.CUSTOM, managed: false, origin: null, originHash: null, principles: [] });
      mutations.setSelectedNode({ type: 'root' });
      return;
    }
    if (!standardId) return;
    setLoading(true);
    getStandard(standardId)
      .then((data) => { setStandard(data); mutations.setSelectedNode({ type: 'root' }); setError(null); })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [standardId, isNew]);

  const save = useCallback(async () => {
    const result = await mutations.save();
    if (result?.error) setError(result.error);
    else setError(null);
  }, [mutations.save]);

  const editable = standard && !standard.managed;

  return {
    standard,
    loading,
    error,
    dirty,
    editable,
    selectedNode: mutations.selectedNode,
    setSelectedNode: mutations.setSelectedNode,
    updateField: mutations.updateField,
    addPrinciple: mutations.addPrinciple,
    removePrinciple: mutations.removePrinciple,
    addRequirement: mutations.addRequirement,
    removeRequirement: mutations.removeRequirement,
    save,
  };
}
