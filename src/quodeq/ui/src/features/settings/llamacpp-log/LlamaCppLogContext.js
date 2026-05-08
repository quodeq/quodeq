import { createContext, useContext } from 'react';

export const LlamaCppLogContext = createContext(null);

export function useLlamaCppLog() {
  const ctx = useContext(LlamaCppLogContext);
  if (!ctx) throw new Error('useLlamaCppLog must be used inside <LlamaCppLogProvider>');
  return ctx;
}
