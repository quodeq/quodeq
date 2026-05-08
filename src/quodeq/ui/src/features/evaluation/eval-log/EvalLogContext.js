import { createContext, useContext } from 'react';

export const EvalLogContext = createContext(null);

// Split out the high-frequency `logs` value so consumers of the stable
// (status / openLog / closeLog) context don't re-render on every appended
// line. Only the in-pane log view subscribes here.
export const EvalLogLogsContext = createContext({ logs: [] });

export function useEvalLog() {
  const ctx = useContext(EvalLogContext);
  if (!ctx) throw new Error('useEvalLog must be used inside <EvalLogProvider>');
  return ctx;
}

export function useEvalLogLogs() {
  return useContext(EvalLogLogsContext);
}
