import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import ConsoleLogViewer from '../components/ConsoleLogViewer.jsx';
import { EvalLogContext } from './EvalLogContext.js';
import { useJobLogStream } from './useJobLogStream.js';

const STREAM_STATUS_WORD = {
  idle: '',
  streaming: 'running',
  done: 'completed',
  error: 'error',
};

const JOB_STATUS_WORD = {
  running: 'running',
  done: 'completed',
  failed: 'failed',
  cancelled: 'cancelled',
  lost: 'lost',
};

function statusWord(jobStatus, streamStatus, terminalState) {
  // The SSE-emitted terminal state — when present — is the most accurate:
  // the server reads the runner's status.json (or in-memory job) at the
  // moment the stream ends, so it knows *why* the run stopped even when
  // ScanProgress isn't mounted to push the lifecycle reason.
  if (terminalState && JOB_STATUS_WORD[terminalState]) return JOB_STATUS_WORD[terminalState];
  // Specific terminal job states win over a generic stream "done".
  if (jobStatus === 'failed' || jobStatus === 'cancelled' || jobStatus === 'lost') {
    return JOB_STATUS_WORD[jobStatus];
  }
  // Otherwise the stream's terminal states override a stale "running"
  // jobStatus (e.g. progress poll hasn't caught up, or ScanProgress
  // unmounted before flipping status).
  if (streamStatus === 'done') return 'completed';
  if (streamStatus === 'error') return 'error';
  if (jobStatus && JOB_STATUS_WORD[jobStatus]) return JOB_STATUS_WORD[jobStatus];
  return STREAM_STATUS_WORD[streamStatus] || '';
}

function buildSpec({ jobId, jobStatus, logs, status, terminalState }) {
  if (!jobId) return null;
  const word = statusWord(jobStatus, status, terminalState);
  const parts = ['log evaluation'];
  if (word) parts.push(word);
  parts.push(jobId);
  return {
    id: 'eval-log',
    type: 'eval-log',
    title: parts.join(' · '),
    render: () => <ConsoleLogViewer logs={logs} />,
  };
}

const WINDOW_ID = 'eval-log';

export function EvalLogProvider({ children }) {
  const [activeJobId, setActiveJobId] = useState(null);
  const [activeJobLabel, setActiveJobLabel] = useState(null);
  const [activeJobStatus, setActiveJobStatus] = useState(null);
  const { logs, status, terminalState } = useJobLogStream(activeJobId);
  const { addWindow, removeWindow, replaceWindow, hasWindow } = useSidePane();

  const spec = useMemo(
    () => buildSpec({ jobId: activeJobId, jobStatus: activeJobStatus, logs, status, terminalState }),
    [activeJobId, activeJobStatus, logs, status, terminalState],
  );

  useEffect(() => {
    if (spec) replaceWindow(spec);
  }, [spec, replaceWindow]);

  const openLog = useCallback((jobId, label = null, jobStatus = null) => {
    if (!jobId) return;
    setActiveJobId(jobId);
    setActiveJobLabel(label);
    setActiveJobStatus(jobStatus);
    const fresh = buildSpec({ jobId, jobStatus, logs: [], status: 'streaming' });
    addWindow(fresh);
    replaceWindow(fresh);
  }, [addWindow, replaceWindow]);

  const updateJobStatus = useCallback((jobStatus) => {
    setActiveJobStatus(jobStatus ?? null);
  }, []);

  const closeLog = useCallback(() => {
    setActiveJobId(null);
    setActiveJobLabel(null);
    setActiveJobStatus(null);
    removeWindow(WINDOW_ID);
  }, [removeWindow]);

  // If the user closes the side-pane window via the X (or Escape closes
  // all panes), sync our active-job state — otherwise `consoleOpen` stays
  // truthy and the Console button needs two clicks to reopen.
  useEffect(() => {
    if (activeJobId && !hasWindow(WINDOW_ID)) {
      setActiveJobId(null);
      setActiveJobLabel(null);
      setActiveJobStatus(null);
    }
  }, [activeJobId, hasWindow]);

  const value = useMemo(
    () => ({ activeJobId, activeJobLabel, activeJobStatus, status, openLog, closeLog, updateJobStatus }),
    [activeJobId, activeJobLabel, activeJobStatus, status, openLog, closeLog, updateJobStatus],
  );

  return <EvalLogContext.Provider value={value}>{children}</EvalLogContext.Provider>;
}
