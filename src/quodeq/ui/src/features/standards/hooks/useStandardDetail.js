import { useState, useEffect, useCallback } from 'react';
import { getStandard, createStandard, updateStandard } from '../../../api/index.js';
import { generateRequirementId } from '../utils.js';
import { deepClone } from '../../../utils/deepClone.js';
import { STANDARD_TYPES } from './useStandards.js';

function useTreeMutations(setStandard, setDirty, setSelectedNode) {
  const addPrinciple = useCallback(() => {
    setStandard((prev) => {
      const next = deepClone(prev);
      next.principles.push({ name: '', description: '', requirements: [] });
      setSelectedNode({ type: 'principle', index: next.principles.length - 1 });
      return next;
    });
    setDirty(true);
  }, [setStandard, setDirty]);

  const removePrinciple = useCallback((index) => {
    setStandard((prev) => {
      const next = deepClone(prev);
      next.principles.splice(index, 1);
      return next;
    });
    setDirty(true);
    setSelectedNode({ type: 'root' });
  }, [setStandard, setDirty]);

  const addRequirement = useCallback((principleIndex) => {
    setStandard((prev) => {
      const next = deepClone(prev);
      const principle = next.principles[principleIndex];
      const seq = (principle.requirements?.length || 0) + 1;
      const autoId = generateRequirementId(next.id, principle.name, seq);
      principle.requirements.push({ id: autoId, text: '', description: '', refs: [] });
      setSelectedNode({ type: 'requirement', principleIndex, reqIndex: principle.requirements.length - 1 });
      return next;
    });
    setDirty(true);
  }, [setStandard, setDirty]);

  const removeRequirement = useCallback((principleIndex, reqIndex) => {
    setStandard((prev) => {
      const next = deepClone(prev);
      next.principles[principleIndex].requirements.splice(reqIndex, 1);
      return next;
    });
    setDirty(true);
    setSelectedNode({ type: 'principle', index: principleIndex });
  }, [setStandard, setDirty]);

  return { addPrinciple, removePrinciple, addRequirement, removeRequirement };
}

function useStandardMutations(standard, setStandard, setDirty, standardId, isNew) {
  const [selectedNode, setSelectedNode] = useState(null);

  // Deep clone is required here to ensure React detects state changes via
  // referential inequality across the entire nested standard tree (principles
  // -> requirements). The tree is small (typically <50 nodes), so JSON
  // round-trip cost is negligible.
  const updateField = useCallback((path, value) => {
    setStandard((prev) => {
      const next = deepClone(prev);
      let target = next;
      for (let i = 0; i < path.length - 1; i++) target = target[path[i]];
      target[path[path.length - 1]] = value;
      return next;
    });
    setDirty(true);
  }, [setStandard, setDirty]);

  const tree = useTreeMutations(setStandard, setDirty, setSelectedNode);

  const save = useCallback(async () => {
    if (!standard) return;
    if (!standard.id) return { error: 'ID is required' };
    if (!standard.name) return { error: 'Name is required' };
    try {
      if (isNew) { await createStandard(standard); } else { await updateStandard(standard.id, standard); }
      setDirty(false);
      return { error: null };
    } catch (err) { return { error: err.message }; }
  }, [standard, isNew, setDirty]);

  return { selectedNode, setSelectedNode, updateField, ...tree, save };
}

export function useStandardDetail(standardId, isNew) {
  const [standard, setStandard] = useState(null);
  const [loading, setLoading] = useState(!isNew);
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);

  const mutations = useStandardMutations(standard, setStandard, setDirty, standardId, isNew);

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
