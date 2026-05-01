import { createContext, useContext } from 'react';

export const EvalLogContext = createContext(null);

export function useEvalLog() {
  const ctx = useContext(EvalLogContext);
  if (!ctx) throw new Error('useEvalLog must be used inside <EvalLogProvider>');
  return ctx;
}
