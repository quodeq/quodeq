import { useCallback, useEffect, useMemo, useState } from 'react';
import { SidePaneContext } from './SidePaneContext.jsx';
import { clampSidePaneWidth } from './paneWidthMath.js';
import { readString, removeKey, writeString } from '../../adapters/storage.js';
import { t } from '../../strings/index.js';
import { useRegisteredSpecs } from './hooks/useRegisteredSpecs.js';

const STORAGE_KEY = 'quodeq.sidePaneWidth';
const LEGACY_STORAGE_KEY = 'quodeq.reportPaneWidth';
const DEFAULT_WIDTH_PX = 560;
const MAX_WINDOWS = 3;
const NOTICE_DISMISS_MS = 4000;
// Typical desktop viewport width, used only when `window` is unavailable
// (SSR / non-browser test environment) so clampSidePaneWidth still has a
// sane bound to clamp against.
const FALLBACK_VIEWPORT_WIDTH_PX = 1920;
const AT_CAP_MESSAGE = t('sidePane.atCap', { max: MAX_WINDOWS });

/**
 * The transient side-pane notice. The whole toast dismisses on click, the mouse
 * convenience its `cursor: pointer` promises, and the dismiss button is the
 * keyboard-reachable control; two paths to the same dismiss are fine, but the
 * button stops its click so one press does not dismiss twice.
 *
 * The shell is `role="presentation"`, because jsx-a11y (rightly) refuses mouse
 * handlers on a `role="status"` element and the shell really is presentational.
 * It carries no live region at all: it is keyed by notice, so it remounts with
 * its text already in place, which is not reliably announced. The live region
 * is the persistent one the provider renders beside it.
 */
export function SidePaneToast({ notice, onDismiss }) {
  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(onDismiss, NOTICE_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [notice, onDismiss]);
  if (!notice) return null;
  function handleDismissClick(e) {
    e.stopPropagation();
    onDismiss();
  }
  return (
    <div
      className="job-error-toast side-pane-toast"
      role="presentation"
      onClick={onDismiss}
    >
      {notice.message}
      <button
        type="button"
        className="side-pane-toast__dismiss"
        aria-label={t('common.dismissNotificationAria')}
        onClick={handleDismissClick}
      >
        ×
      </button>
    </div>
  );
}

function readStoredWidth() {
  let raw = readString(STORAGE_KEY);
  if (raw == null) {
    // One-time migration from the pre-rename key.
    const legacy = readString(LEGACY_STORAGE_KEY);
    if (legacy != null) {
      writeString(STORAGE_KEY, legacy);
      removeKey(LEGACY_STORAGE_KEY);
      raw = legacy;
    }
  }
  const n = raw ? parseInt(raw, 10) : NaN;
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_WIDTH_PX;
}

function writeStoredWidth(px) {
  writeString(STORAGE_KEY, String(px));
}

// Transient notice surfaced as a toast (e.g. "max panels open"). The `key`
// forces a fresh mount when the same message is shown twice in a row, so
// the auto-dismiss timer resets and the slide-in animation replays.
function useNoticeState() {
  const [notice, setNotice] = useState(null);

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

  return { notice, showAtCapNotice, clearNotice, showToast };
}

// A spec with no id cannot be tracked, opened or closed, so every action
// ignores it rather than pushing an unidentifiable window.
function isOpenableSpec(spec) {
  return Boolean(spec && spec.id);
}

function useWindowActions({ windows, setWindows, showAtCapNotice }) {
  const hasWindow = useCallback(
    (id) => windows.some((w) => w.id === id),
    [windows],
  );

  // Append unless the dock is full, in which case the caller's click turns
  // into the at-cap snackbar instead.
  const pushWithinCap = useCallback((spec) => {
    if (windows.length >= MAX_WINDOWS) {
      showAtCapNotice();
      return;
    }
    setWindows((prev) => [...prev, spec]);
  }, [windows, showAtCapNotice]);

  const addWindow = useCallback((spec) => {
    if (!isOpenableSpec(spec)) return;
    if (hasWindow(spec.id)) return;
    pushWithinCap(spec);
  }, [hasWindow, pushWithinCap]);

  const removeWindow = useCallback((id) => {
    setWindows((prev) => prev.filter((w) => w.id !== id));
  }, []);

  const replaceWindow = useCallback((spec) => {
    if (!isOpenableSpec(spec)) return;
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
    if (!isOpenableSpec(spec)) return;
    if (hasWindow(spec.id)) {
      setWindows((prev) => prev.filter((w) => w.id !== spec.id));
      return;
    }
    pushWithinCap(spec);
  }, [hasWindow, pushWithinCap]);

  const closeAll = useCallback(() => setWindows([]), []);

  return { hasWindow, addWindow, removeWindow, replaceWindow, toggleWindow, closeAll };
}

// Sync the open width into a CSS variable on the root so the grid template can read it.
function useSidePaneWidthCssSync(isOpen, paneWidth) {
  useEffect(() => {
    const root = document.documentElement;
    if (isOpen) {
      root.style.setProperty('--side-pane-width', `${paneWidth}px`);
    } else {
      root.style.setProperty('--side-pane-width', '0px');
    }
  }, [isOpen, paneWidth]);
}

// Escape closes all windows when the pane is open.
function useEscapeClosesAll(isOpen, setWindows) {
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
}

export function SidePaneProvider({ children }) {
  const [windows, setWindows] = useState([]);
  const [paneWidth, setPaneWidthState] = useState(readStoredWidth);

  const isOpen = windows.length > 0;

  const { notice, showAtCapNotice, clearNotice, showToast } = useNoticeState();
  const { hasWindow, addWindow, removeWindow, replaceWindow, toggleWindow, closeAll } = useWindowActions({ windows, setWindows, showAtCapNotice });

  const { registerSpec, unregisterSpec, getRegisteredSpec } = useRegisteredSpecs();

  const setPaneWidth = useCallback((px) => {
    const next = clampSidePaneWidth(px, typeof window !== 'undefined' ? window.innerWidth : FALLBACK_VIEWPORT_WIDTH_PX);
    setPaneWidthState(next);
    writeStoredWidth(next);
  }, []);

  useSidePaneWidthCssSync(isOpen, paneWidth);
  useEscapeClosesAll(isOpen, setWindows);

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
      {/* Always mounted, text toggled, and deliberately outside the keyed
          shell: a live region that mounts with its text in it is not
          reliably announced. */}
      <span role="status" className="sr-only">{notice ? notice.message : ''}</span>
      <SidePaneToast key={notice?.key} notice={notice} onDismiss={clearNotice} />
    </SidePaneContext.Provider>
  );
}
