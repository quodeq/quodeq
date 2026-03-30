import { useState, useEffect, useCallback } from 'react';
import { getStandard, createStandard, updateStandard } from '../../../api/index.js';
import { generateRequirementId } from '../utils.js';

export function useStandardDetail(standardId, isNew) {
  const [standard, setStandard] = useState(null);
  const [loading, setLoading] = useState(!isNew);
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);

  useEffect(() => {
    if (isNew) {
      setStandard({ id: '', name: '', description: '', weight: 1.0, source: '', type: 'custom', managed: false, origin: null, originHash: null, principles: [] });
      setSelectedNode({ type: 'root' });
      return;
    }
    if (!standardId) return;
    setLoading(true);
    getStandard(standardId)
      .then((data) => { setStandard(data); setSelectedNode({ type: 'root' }); setError(null); })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [standardId, isNew]);

  const updateField = useCallback((path, value) => {
    setStandard((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      let target = next;
      for (let i = 0; i < path.length - 1; i++) target = target[path[i]];
      target[path[path.length - 1]] = value;
      return next;
    });
    setDirty(true);
  }, []);

  const addPrinciple = useCallback(() => {
    setStandard((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.principles.push({ name: '', description: '', requirements: [] });
      setSelectedNode({ type: 'principle', index: next.principles.length - 1 });
      return next;
    });
    setDirty(true);
  }, []);

  const removePrinciple = useCallback((index) => {
    setStandard((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.principles.splice(index, 1);
      return next;
    });
    setDirty(true);
    setSelectedNode({ type: 'root' });
  }, []);

  const addRequirement = useCallback((principleIndex) => {
    setStandard((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      const principle = next.principles[principleIndex];
      const seq = (principle.requirements?.length || 0) + 1;
      const autoId = generateRequirementId(next.id, principle.name, seq);
      principle.requirements.push({ id: autoId, text: '', description: '', refs: [] });
      setSelectedNode({ type: 'requirement', principleIndex, reqIndex: principle.requirements.length - 1 });
      return next;
    });
    setDirty(true);
  }, []);

  const removeRequirement = useCallback((principleIndex, reqIndex) => {
    setStandard((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.principles[principleIndex].requirements.splice(reqIndex, 1);
      return next;
    });
    setDirty(true);
    setSelectedNode({ type: 'principle', index: principleIndex });
  }, []);

  const save = useCallback(async () => {
    if (!standard) return;
    if (!standard.id) { setError('ID is required'); return; }
    if (!standard.name) { setError('Name is required'); return; }
    try {
      if (isNew) { await createStandard(standard); } else { await updateStandard(standard.id, standard); }
      setDirty(false);
      setError(null);
    } catch (err) { setError(err.message); }
  }, [standard, isNew]);

  const editable = standard && !standard.managed;

  return { standard, loading, error, dirty, editable, selectedNode, setSelectedNode, updateField, addPrinciple, removePrinciple, addRequirement, removeRequirement, save };
}
