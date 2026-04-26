import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ReportViewerContext } from './ReportViewerContext.jsx';

const STORAGE_KEY = 'quodeq.reportPaneWidth';
const DEFAULT_WIDTH_PX = 560;

function readStoredWidth() {
  try {
    const raw = typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY);
    const n = raw ? parseInt(raw, 10) : NaN;
    return Number.isFinite(n) && n > 0 ? n : DEFAULT_WIDTH_PX;
  } catch {
    return DEFAULT_WIDTH_PX;
  }
}

function writeStoredWidth(px) {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, String(px));
  } catch {
    /* quota / disabled — ignore */
  }
}

export function ReportViewerProvider({ children }) {
  const [current, setCurrent] = useState(null); // { title, markdown } | null
  const [isOpen, setIsOpen] = useState(false);
  const [paneWidth, setPaneWidthState] = useState(readStoredWidth);

  const openReport = useCallback(({ title, markdown }) => {
    setCurrent({ title, markdown });
    setIsOpen(true);
  }, []);

  const closeReport = useCallback(() => {
    setIsOpen(false);
  }, []);

  const setPaneWidth = useCallback((px) => {
    setPaneWidthState(px);
    writeStoredWidth(px);
  }, []);

  // Sync the open width into a CSS variable on the root so the grid template can read it.
  useEffect(() => {
    const root = document.documentElement;
    if (isOpen) {
      root.style.setProperty('--report-pane-width', `${paneWidth}px`);
    } else {
      root.style.setProperty('--report-pane-width', '0px');
    }
  }, [isOpen, paneWidth]);

  // Escape closes when open.
  useEffect(() => {
    if (!isOpen) return undefined;
    function onKey(e) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setIsOpen(false);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen]);

  const value = useMemo(
    () => ({ current, isOpen, paneWidth, openReport, closeReport, setPaneWidth }),
    [current, isOpen, paneWidth, openReport, closeReport, setPaneWidth]
  );

  return (
    <ReportViewerContext.Provider value={value}>
      {children}
    </ReportViewerContext.Provider>
  );
}
