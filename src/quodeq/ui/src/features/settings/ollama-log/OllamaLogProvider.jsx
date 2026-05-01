import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import ConsoleLogViewer from '../../evaluation/components/ConsoleLogViewer.jsx';
import { OllamaLogContext } from './OllamaLogContext.js';
import { useOllamaLogStream } from './useOllamaLogStream.js';

const WINDOW_ID = 'ollama-log';

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
    title: `Ollama log${STATUS_LABEL[status] || ''}`,
    render: () => <ConsoleLogViewer logs={logs} />,
    copy: () => logs.join('\n'),
    download: () => ({ filename: 'ollama-server.log', body: logs.join('\n') }),
  };
}

export function OllamaLogProvider({ children }) {
  const [open, setOpen] = useState(false);
  const { logs, status } = useOllamaLogStream(open);
  const { addWindow, removeWindow, replaceWindow, hasWindow } = useSidePane();

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
    () => ({ open, openLog, closeLog }),
    [open, openLog, closeLog],
  );

  return <OllamaLogContext.Provider value={value}>{children}</OllamaLogContext.Provider>;
}
