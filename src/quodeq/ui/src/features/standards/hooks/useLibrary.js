import { useState, useCallback } from 'react';
import { listLibrary, importFromLibrary } from '../../../api/index.js';

export function useLibrary() {
  const [libraryStandards, setLibraryStandards] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchLibrary = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listLibrary();
      setLibraryStandards(data);
      setError(null);
    }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);

  const importStandard = useCallback(async (filePath) => {
    try {
      await importFromLibrary(filePath);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to import standard');
      throw err;
    }
  }, []);

  return { libraryStandards, loading, error, fetchLibrary, importStandard };
}
