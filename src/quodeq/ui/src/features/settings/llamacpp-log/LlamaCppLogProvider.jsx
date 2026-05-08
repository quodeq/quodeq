import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import ConsoleLogViewer from '../../evaluation/components/ConsoleLogViewer.jsx';
import { LlamaCppLogContext } from './LlamaCppLogContext.js';
import { useLlamaCppLogStream } from './useLlamaCppLogStream.js';

const WINDOW_ID = 'llamacpp-log';

const STATUS_LABEL = {
  idle: '',
  streaming: ' · running',
  done: ' · stopped',
  error: ' · unavailable',
};

function buildSpec(logs, status) {
  return {
    id: WINDOW_ID,
    type: WINDOW_ID,
    title: `llama.cpp log${STATUS_LABEL[status] || ''}`,
    render: () => <ConsoleLogViewer logs={logs} />,
  };
}

export function LlamaCppLogProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [available, setAvailable] = useState(false);
  const { logs, status } = useLlamaCppLogStream(open);
  const { addWindow, removeWindow, replaceWindow, hasWindow } = useSidePane();

  // The console toggle is hidden unless the server reports a configured
  // LLAMACPP_LOG_FILE. Probe once on mount; the result is stable for the
  // session since the env var is set at server-launch time.
  useEffect(() => {
    let cancelled = false;
    fetch('/api/llamacpp/logs/available')
      .then((r) => (r.ok ? r.json() : { available: false }))
      .then((data) => {
        if (!cancelled) setAvailable(Boolean(data?.available));
      })
      .catch(() => {
        if (!cancelled) setAvailable(false);
      });
    return () => { cancelled = true; };
  }, []);

  const spec = useMemo(() => (open ? buildSpec(logs, status) : null), [open, logs, status]);

  useEffect(() => {
    if (spec) replaceWindow(spec);
  }, [spec, replaceWindow]);

  const openLog = useCallback(() => {
    setOpen(true);
    const fresh = buildSpec([], 'streaming');
    addWindow(fresh);
    replaceWindow(fresh);
  }, [addWindow, replaceWindow]);

  const closeLog = useCallback(() => {
    setOpen(false);
    removeWindow(WINDOW_ID);
  }, [removeWindow]);

  // Sync open state if user closes the window via the X.
  useEffect(() => {
    if (open && !hasWindow(WINDOW_ID)) setOpen(false);
  }, [open, hasWindow]);

  const value = useMemo(
    () => ({ open, available, openLog, closeLog }),
    [open, available, openLog, closeLog],
  );

  return <LlamaCppLogContext.Provider value={value}>{children}</LlamaCppLogContext.Provider>;
}
