import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import ConsoleLogViewer from '../../evaluation/components/ConsoleLogViewer.jsx';
import { ServerLogContext } from './ServerLogContext.js';
import { useServerLogPoll } from './useServerLogPoll.js';

const WINDOW_ID = 'server-log';

function buildSpec(logs) {
  return {
    id: WINDOW_ID,
    type: WINDOW_ID,
    title: 'Server log',
    render: () => <ConsoleLogViewer logs={logs} />,
  };
}

export function ServerLogProvider({ children }) {
  const [open, setOpen] = useState(false);
  const { logs } = useServerLogPoll(open);
  const { addWindow, removeWindow, replaceWindow, hasWindow } = useSidePane();

  const spec = useMemo(() => (open ? buildSpec(logs) : null), [open, logs]);

  useEffect(() => {
    if (spec) replaceWindow(spec);
  }, [spec, replaceWindow]);

  const openLog = useCallback(() => {
    setOpen(true);
    const fresh = buildSpec([]);
    addWindow(fresh);
    replaceWindow(fresh);
  }, [addWindow, replaceWindow]);

  const closeLog = useCallback(() => {
    setOpen(false);
    removeWindow(WINDOW_ID);
  }, [removeWindow]);

  // If the user closes the side-pane window via the X, sync our open state.
  useEffect(() => {
    if (open && !hasWindow(WINDOW_ID)) setOpen(false);
  }, [open, hasWindow]);

  const value = useMemo(
    () => ({ open, openLog, closeLog }),
    [open, openLog, closeLog],
  );

  return <ServerLogContext.Provider value={value}>{children}</ServerLogContext.Provider>;
}
