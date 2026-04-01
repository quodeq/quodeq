import { useState, useEffect, useCallback } from 'react';
import { listStandards, deleteStandard, duplicateStandard } from '../../../api/index.js';

const STANDARD_TYPES = { BUILTIN: 'builtin', QUODEQ: 'quodeq', COMMUNITY: 'community', CUSTOM: 'custom' };

export function useStandards() {
  const [standards, setStandards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(() => {
    setLoading(true);
    listStandards()
      .then((data) => { setStandards(data); setError(null); })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleDelete = useCallback(async (id) => { await deleteStandard(id); refresh(); }, [refresh]);
  const handleDuplicate = useCallback(async (id, newId) => { await duplicateStandard(id, newId); refresh(); }, [refresh]);

  const grouped = {
    [STANDARD_TYPES.BUILTIN]: standards.filter((s) => s.type === STANDARD_TYPES.BUILTIN),
    [STANDARD_TYPES.QUODEQ]: standards.filter((s) => s.type === STANDARD_TYPES.QUODEQ),
    [STANDARD_TYPES.COMMUNITY]: standards.filter((s) => s.type === STANDARD_TYPES.COMMUNITY),
    [STANDARD_TYPES.CUSTOM]: standards.filter((s) => s.type === STANDARD_TYPES.CUSTOM),
  };

  return { standards, grouped, loading, error, refresh, handleDelete, handleDuplicate };
}
