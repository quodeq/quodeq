import ConsoleLogViewer from '../../evaluation/components/ConsoleLogViewer.jsx';
import { OllamaLogContext } from './OllamaLogContext.js';
import { useOllamaLogStream } from './useOllamaLogStream.js';
import { useLogWindow } from '../_shared/useLogWindow.js';
import { t } from '../../../strings/index.js';
import { LOG_STREAM_STATUS } from '../../../vocab/logStreamStatus.js';

const WINDOW_ID = 'ollama-log';

const STATUS_LABEL = {
  [LOG_STREAM_STATUS.IDLE]: '',
  [LOG_STREAM_STATUS.STREAMING]: ' · running',
  [LOG_STREAM_STATUS.DONE]: ' · stopped',
  [LOG_STREAM_STATUS.ERROR]: t('settings.logUnavailable'),
};

// `opening` is true only for the synchronous "just clicked open" spec
// useLogWindow builds before useOllamaLogStream's own effect has flipped
// status from 'idle' to 'streaming' — without it the freshly opened window
// would paint with no status suffix for one commit.
function buildSpec({ logs, firstSeq, status }, { open: opening } = {}) {
  const effectiveStatus = opening ? LOG_STREAM_STATUS.STREAMING : status;
  return {
    id: WINDOW_ID,
    type: WINDOW_ID,
    title: `${t('settings.ollamaLogTitle')}${STATUS_LABEL[effectiveStatus] || ''}`,
    render: () => <ConsoleLogViewer logs={logs} firstSeq={firstSeq} />,
  };
}

export function OllamaLogProvider({ children }) {
  const value = useLogWindow({ windowId: WINDOW_ID, useLogSource: useOllamaLogStream, buildSpec });
  return <OllamaLogContext.Provider value={value}>{children}</OllamaLogContext.Provider>;
}
