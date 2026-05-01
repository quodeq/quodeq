import { createContext, useContext } from 'react';

export const ServerLogContext = createContext(null);

export function useServerLog() {
  const ctx = useContext(ServerLogContext);
  if (!ctx) throw new Error('useServerLog must be used inside <ServerLogProvider>');
  return ctx;
}
