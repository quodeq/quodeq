import { createContext, useContext } from 'react';

export const OllamaLogContext = createContext(null);

export function useOllamaLog() {
  const ctx = useContext(OllamaLogContext);
  if (!ctx) throw new Error('useOllamaLog must be used inside <OllamaLogProvider>');
  return ctx;
}
