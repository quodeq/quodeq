import { useState, useEffect, useCallback } from 'react';
import { listStandards, deleteStandard, duplicateStandard } from '../../../api/index.js';

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
    builtin: standards.filter((s) => s.type === 'builtin'),
    community: standards.filter((s) => s.type === 'community'),
    custom: standards.filter((s) => s.type === 'custom'),
  };

  return { standards, grouped, loading, error, refresh, handleDelete, handleDuplicate };
}
