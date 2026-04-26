import { createContext, useContext } from 'react';

export const ReportViewerContext = createContext(null);

export function useReportViewer() {
  const ctx = useContext(ReportViewerContext);
  if (ctx === null) {
    throw new Error('useReportViewer must be used inside a <ReportViewerProvider>');
  }
  return ctx;
}
