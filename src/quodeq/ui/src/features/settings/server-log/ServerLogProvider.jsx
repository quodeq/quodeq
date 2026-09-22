import ConsoleLogViewer from '../../evaluation/components/ConsoleLogViewer.jsx';
import { ServerLogContext } from './ServerLogContext.js';
import { useServerLogPoll } from './useServerLogPoll.js';
import { useLogWindow } from '../_shared/useLogWindow.js';
import { t } from '../../../strings/index.js';

const WINDOW_ID = 'server-log';

function buildSpec({ logs }) {
  return {
    id: WINDOW_ID,
    type: WINDOW_ID,
    title: t('settings.serverLogTitle'),
    render: () => <ConsoleLogViewer logs={logs} />,
  };
}

export function ServerLogProvider({ children }) {
  const value = useLogWindow({ windowId: WINDOW_ID, useLogSource: useServerLogPoll, buildSpec });
  return <ServerLogContext.Provider value={value}>{children}</ServerLogContext.Provider>;
}
