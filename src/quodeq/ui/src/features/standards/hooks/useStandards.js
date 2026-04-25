import { useState, useEffect, useCallback, useMemo } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';

export const STANDARD_TYPES = { BUILTIN: 'builtin', QUODEQ: 'quodeq', COMMUNITY: 'community', CUSTOM: 'custom' };

export function useStandards() {
  const { listStandards, deleteStandard, duplicateStandard } = useApi();
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

  const handleDelete = useCallback(async (id) => {
    try {
      await deleteStandard(id);
      refresh();
    } catch (err) {
      setError(err.message || 'Failed to delete standard');
    }
  }, [refresh]);
  const handleDuplicate = useCallback(async (id, newId) => {
    try {
      await duplicateStandard(id, newId);
      refresh();
    } catch (err) {
      setError(err.message || 'Failed to duplicate standard');
    }
  }, [refresh]);

  const grouped = useMemo(() => {
    const g = {
      [STANDARD_TYPES.BUILTIN]: [],
      [STANDARD_TYPES.QUODEQ]: [],
      [STANDARD_TYPES.COMMUNITY]: [],
      [STANDARD_TYPES.CUSTOM]: [],
    };
    for (const s of standards) {
      if (g[s.type]) g[s.type].push(s);
    }
    return g;
  }, [standards]);

  return { standards, grouped, loading, error, refresh, handleDelete, handleDuplicate };
}
