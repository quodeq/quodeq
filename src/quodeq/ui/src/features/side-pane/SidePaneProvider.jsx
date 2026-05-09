import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { SidePaneContext } from './SidePaneContext.jsx';
import { clampSidePaneWidth } from './paneWidthMath.js';

const STORAGE_KEY = 'quodeq.sidePaneWidth';
const LEGACY_STORAGE_KEY = 'quodeq.reportPaneWidth';
const DEFAULT_WIDTH_PX = 560;
const MAX_WINDOWS = 3;
const NOTICE_DISMISS_MS = 4000;
const AT_CAP_MESSAGE = `Up to ${MAX_WINDOWS} panels can be open at once. Close one first.`;

function SidePaneToast({ notice, onDismiss }) {
  useEffect(() => {
    if (!notice) return undefined;
    const t = setTimeout(onDismiss, NOTICE_DISMISS_MS);
    return () => clearTimeout(t);
  }, [notice, onDismiss]);
  if (!notice) return null;
  return (
    <div
      className="job-error-toast side-pane-toast"
      onClick={onDismiss}
      role="status"
      aria-live="polite"
    >
      {notice.message}
    </div>
  );
}

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
  // Transient notice surfaced as a toast (e.g. "max panels open"). The `key`
  // forces a fresh mount when the same message is shown twice in a row, so
  // the auto-dismiss timer resets and the slide-in animation replays.
  const [notice, setNotice] = useState(null);

  const isOpen = windows.length > 0;

  const hasWindow = useCallback(
    (id) => windows.some((w) => w.id === id),
    [windows],
  );

  const showAtCapNotice = useCallback(() => {
    setNotice({ message: AT_CAP_MESSAGE, key: Date.now() });
  }, []);

  const clearNotice = useCallback(() => setNotice(null), []);

  // Generic snackbar trigger for callers outside the side-pane (e.g. the
  // evaluation form's "select at least one standard" hint, or App.jsx's
  // "an evaluation is in progress" block on Add Project). Reuses the same
  // visual + auto-dismiss as the side-pane's own at-cap notice.
  const showToast = useCallback((message) => {
    if (!message) return;
    setNotice({ message, key: Date.now() });
  }, []);

  const addWindow = useCallback((spec) => {
    if (!spec || !spec.id) return;
    if (windows.some((w) => w.id === spec.id)) return;
    if (windows.length >= MAX_WINDOWS) {
      showAtCapNotice();
      return;
    }
    setWindows((prev) => [...prev, spec]);
  }, [windows, showAtCapNotice]);

  const removeWindow = useCallback((id) => {
    setWindows((prev) => prev.filter((w) => w.id !== id));
  }, []);

  const replaceWindow = useCallback((spec) => {
    if (!spec || !spec.id) return;
    setWindows((prev) => {
      const idx = prev.findIndex((w) => w.id === spec.id);
      if (idx === -1) return prev;
      if (prev[idx] === spec) return prev;
      const next = prev.slice();
      next[idx] = spec;
      return next;
    });
  }, []);

  const toggleWindow = useCallback((spec) => {
    if (!spec || !spec.id) return;
    if (windows.some((w) => w.id === spec.id)) {
      setWindows((prev) => prev.filter((w) => w.id !== spec.id));
      return;
    }
    if (windows.length >= MAX_WINDOWS) {
      showAtCapNotice();
      return;
    }
    setWindows((prev) => [...prev, spec]);
  }, [windows, showAtCapNotice]);

  const closeAll = useCallback(() => setWindows([]), []);

  const [registeredSpecs, setRegisteredSpecs] = useState({}); // { [type]: spec }

  const registerSpec = useCallback((type, spec) => {
    setRegisteredSpecs((prev) => {
      if (prev[type] === spec) return prev;
      return { ...prev, [type]: spec };
    });
  }, []);

  const unregisterSpec = useCallback((type) => {
    setRegisteredSpecs((prev) => {
      if (!(type in prev)) return prev;
      const next = { ...prev };
      delete next[type];
      return next;
    });
  }, []);

  const getRegisteredSpec = useCallback(
    (type) => registeredSpecs[type] ?? null,
    [registeredSpecs],
  );

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
      addWindow, removeWindow, replaceWindow, toggleWindow, hasWindow, closeAll,
      setPaneWidth, MAX_WINDOWS,
      registerSpec, unregisterSpec, getRegisteredSpec,
      showToast,
    }),
    [windows, isOpen, paneWidth, addWindow, removeWindow, replaceWindow, toggleWindow, hasWindow, closeAll, setPaneWidth, registerSpec, unregisterSpec, getRegisteredSpec, showToast],
  );

  return (
    <SidePaneContext.Provider value={value}>
      {children}
      <SidePaneToast key={notice?.key} notice={notice} onDismiss={clearNotice} />
    </SidePaneContext.Provider>
  );
}
