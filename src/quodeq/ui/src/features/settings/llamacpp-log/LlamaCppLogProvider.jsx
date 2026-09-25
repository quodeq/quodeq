import { useEffect, useMemo, useState } from 'react';
import { LlamaCppLogContext } from './LlamaCppLogContext.js';
import { useLlamaCppLogStream } from './useLlamaCppLogStream.js';
import { useLogWindow } from '../_shared/useLogWindow.js';
import { makeProviderLogSpec } from '../_shared/providerLogSpec.jsx';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';

const WINDOW_ID = 'llamacpp-log';

const buildSpec = makeProviderLogSpec({
  windowId: WINDOW_ID,
  title: () => t('settings.llamaCppLogTitle'),
  emptyOnOpen: true,
});

// The console toggle is hidden unless the server reports a configured
// LLAMACPP_LOG_FILE. Probe once on mount; the result is stable for the
// session since the env var is set at server-launch time.
function useLlamaCppAvailabilityProbe(getLlamacppLogAvailable) {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    let cancelled = false;
    getLlamacppLogAvailable()
      .then((data) => {
        if (!cancelled) setAvailable(Boolean(data?.available));
      })
      .catch(() => {
        if (!cancelled) setAvailable(false);
      });
    return () => { cancelled = true; };
  }, [getLlamacppLogAvailable]);
  return available;
}

export function LlamaCppLogProvider({ children }) {
  const { getLlamacppLogAvailable } = useApi();
  const logWindow = useLogWindow({ windowId: WINDOW_ID, useLogSource: useLlamaCppLogStream, buildSpec });
  const available = useLlamaCppAvailabilityProbe(getLlamacppLogAvailable);

  const value = useMemo(() => ({ ...logWindow, available }), [logWindow, available]);

  return <LlamaCppLogContext.Provider value={value}>{children}</LlamaCppLogContext.Provider>;
}
