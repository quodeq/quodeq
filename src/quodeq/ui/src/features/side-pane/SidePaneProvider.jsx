import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { SidePaneContext } from './SidePaneContext.jsx';
import { clampSidePaneWidth } from './paneWidthMath.js';

const STORAGE_KEY = 'quodeq.sidePaneWidth';
const LEGACY_STORAGE_KEY = 'quodeq.reportPaneWidth';
const DEFAULT_WIDTH_PX = 560;
const MAX_WINDOWS = 3;

function readStoredWidth() {
  try {
    if (typeof localStorage === 'undefined') return DEFAULT_WIDTH_PX;
    let raw = localStorage.getItem(STORAGE_KEY);
    if (raw == null) {
      // One-time migration from the pre-rename key.
      const legacy = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (legacy != null) {
        localStorage.setItem(STORAGE_KEY, legacy);
        localStorage.removeItem(LEGACY_STORAGE_KEY);
        raw = legacy;
      }
    }
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

export function SidePaneProvider({ children }) {
  const [windows, setWindows] = useState([]);
  const [paneWidth, setPaneWidthState] = useState(readStoredWidth);

  const isOpen = windows.length > 0;

  const hasWindow = useCallback(
    (id) => windows.some((w) => w.id === id),
    [windows],
  );

  const addWindow = useCallback((spec) => {
    if (!spec || !spec.id) return;
    setWindows((prev) => {
      if (prev.some((w) => w.id === spec.id)) return prev;
      if (prev.length >= MAX_WINDOWS) return prev;
      return [...prev, spec];
    });
  }, []);

  const removeWindow = useCallback((id) => {
    setWindows((prev) => prev.filter((w) => w.id !== id));
  }, []);

  const toggleWindow = useCallback((spec) => {
    if (!spec || !spec.id) return;
    setWindows((prev) => {
      if (prev.some((w) => w.id === spec.id)) {
        return prev.filter((w) => w.id !== spec.id);
      }
      if (prev.length >= MAX_WINDOWS) return prev;
      return [...prev, spec];
    });
  }, []);

  const closeAll = useCallback(() => setWindows([]), []);

  const setPaneWidth = useCallback((px) => {
    const next = clampSidePaneWidth(px, typeof window !== 'undefined' ? window.innerWidth : 1920);
    setPaneWidthState(next);
    writeStoredWidth(next);
  }, []);

  // Sync the open width into a CSS variable on the root so the grid template can read it.
  useEffect(() => {
    const root = document.documentElement;
    if (isOpen) {
      root.style.setProperty('--side-pane-width', `${paneWidth}px`);
    } else {
      root.style.setProperty('--side-pane-width', '0px');
    }
  }, [isOpen, paneWidth]);

  // Escape closes all windows when the pane is open.
  useEffect(() => {
    if (!isOpen) return undefined;
    function onKey(e) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setWindows([]);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen]);

  const value = useMemo(
    () => ({
      windows, isOpen, paneWidth,
      addWindow, removeWindow, toggleWindow, hasWindow, closeAll,
      setPaneWidth, MAX_WINDOWS,
    }),
    [windows, isOpen, paneWidth, addWindow, removeWindow, toggleWindow, hasWindow, closeAll, setPaneWidth],
  );

  return (
    <SidePaneContext.Provider value={value}>
      {children}
    </SidePaneContext.Provider>
  );
}
