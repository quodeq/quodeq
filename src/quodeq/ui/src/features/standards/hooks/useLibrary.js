import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { standardsKeys } from '../../../api/queryKeys.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

/**
 * The bundled standards library and the import action.
 *
 * `error` carries whichever failed last, the listing or an import.
 * importStandard rethrows after recording the message, so the caller can keep
 * its own dialog open.
 *
 * @returns {{libraryStandards: object[], loading: boolean, error: string|null, importStandard: Function}}
 */
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
