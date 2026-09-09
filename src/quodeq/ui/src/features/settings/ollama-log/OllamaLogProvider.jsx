import ConsoleLogViewer from '../../evaluation/components/ConsoleLogViewer.jsx';
import { OllamaLogContext } from './OllamaLogContext.js';
import { useOllamaLogStream } from './useOllamaLogStream.js';
import { useLogWindow } from '../_shared/useLogWindow.js';
import { t } from '../../../strings/index.js';

const WINDOW_ID = 'ollama-log';

const STATUS_LABEL = {
  idle: '',
  streaming: ' · running',
  done: ' · stopped',
  error: t('settings.logUnavailable'),
};

// `opening` is true only for the synchronous "just clicked open" spec
// useLogWindow builds before useOllamaLogStream's own effect has flipped
// status from 'idle' to 'streaming' — without it the freshly opened window
// would paint with no status suffix for one commit.
function buildSpec({ logs, status }, { open: opening } = {}) {
  const effectiveStatus = opening ? 'streaming' : status;
  return {
    id: WINDOW_ID,
    type: WINDOW_ID,
    title: `${t('settings.ollamaLogTitle')}${STATUS_LABEL[effectiveStatus] || ''}`,
    render: () => <ConsoleLogViewer logs={logs} />,
  };
}

export function OllamaLogProvider({ children }) {
  const value = useLogWindow({ windowId: WINDOW_ID, useLogSource: useOllamaLogStream, buildSpec });
  return <OllamaLogContext.Provider value={value}>{children}</OllamaLogContext.Provider>;
}
