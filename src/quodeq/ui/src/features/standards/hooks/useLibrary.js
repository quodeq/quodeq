import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listLibrary, importFromLibrary } from '../../../api/index.js';
import { standardsKeys } from '../../../api/queryKeys.js';

export function useLibrary() {
  const [importError, setImportError] = useState(null);

  const { data, isLoading, error } = useQuery({
    queryKey: standardsKeys.library(),
    queryFn: () => listLibrary(),
  });

  const importStandard = useCallback(async (filePath) => {
    try {
      await importFromLibrary(filePath);
      setImportError(null);
    } catch (err) {
      setImportError(err.message || 'Failed to import standard');
      throw err;
    }
  }, []);

  return {
    libraryStandards: data || [],
    loading: isLoading,
    error: importError || (error ? error.message : null),
    importStandard,
  };
}
