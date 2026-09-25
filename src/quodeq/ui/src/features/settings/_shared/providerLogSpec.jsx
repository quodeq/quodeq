import ConsoleLogViewer from '../../evaluation/components/ConsoleLogViewer.jsx';
import { t } from '../../../strings/index.js';
import { LOG_STREAM_STATUS } from '../../../vocab/logStreamStatus.js';
import { EMPTY_LOG_BUFFER } from '../../../utils/logBuffer.js';

const STATUS_LABEL = {
  [LOG_STREAM_STATUS.IDLE]: '',
  [LOG_STREAM_STATUS.STREAMING]: ' · running',
  [LOG_STREAM_STATUS.DONE]: ' · stopped',
  [LOG_STREAM_STATUS.ERROR]: t('settings.logUnavailable'),
};

/**
 * The side-pane window spec builder for a local provider's server log, for
 * useLogWindow. The title carries the stream status. A just-opened window
 * (`{ open: true }`) shows as running before the stream's own status catches
 * up.
 * @param {Object} params
 * @param {string} params.windowId Side-pane window id and type.
 * @param {() => string} params.title Window title without the status suffix.
 * @param {boolean} [params.emptyOnOpen=false] Start a just-opened window from
 *   an empty buffer instead of the stream's current one.
 * @returns {(source: {logs: string[], firstSeq: number, status: string}, opts?: {open?: boolean}) => Object}
 */
export function makeProviderLogSpec({ windowId, title, emptyOnOpen = false }) {
  return function buildSpec({ logs, firstSeq, status }, { open: opening } = {}) {
    const effectiveStatus = opening ? LOG_STREAM_STATUS.STREAMING : status;
    const shown = opening && emptyOnOpen ? EMPTY_LOG_BUFFER : { lines: logs, firstSeq };
    return {
      id: windowId,
      type: windowId,
      title: `${title()}${STATUS_LABEL[effectiveStatus] || ''}`,
      render: () => <ConsoleLogViewer logs={shown.lines} firstSeq={shown.firstSeq} />,
    };
  };
}
