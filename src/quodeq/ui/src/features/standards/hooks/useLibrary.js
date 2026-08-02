import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { standardsKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

export function useLibrary() {
  const { listLibrary, importFromLibrary } = useApi();
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
      setImportError(apiErrorMessage(err, 'standards.importStandardFailed'));
      throw err;
    }
  }, [importFromLibrary]);

  return {
    libraryStandards: data || [],
    loading: isLoading,
    error: importError || (error ? error.message : null),
    importStandard,
  };
}
