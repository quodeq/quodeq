/**
 * The shared shell of the Compare header's launcher popovers.
 *
 * The duel trigger and the dimension trigger are the same control — a button
 * that opens a portaled menu anchored to itself, dismissed on outside click
 * or Escape — with different menu contents. The shell lives here so a change
 * to the popover behaviour lands once.
 */
import { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { scoreColorClass } from '../../../utils/formatters.js';
import { launcherMenuPos } from './compareLauncherMenu.js';
import { useLauncherDismiss } from './useLauncherDismiss.js';
import { useLauncherFocus } from './useLauncherFocus.js';
import { score1 } from '../compareFormatters.js';

/**
 * Open/close state, anchor position and dismissal wiring for a launcher.
 *
 * @param {Object} [options]
 * @param {() => void} [options.onClose] Extra state to reset whenever the menu closes.
 * @param {() => void} [options.openDirect] When given, a click runs this instead of opening the menu.
 * @returns {{open: boolean, pos: Object|null, btnRef: Object, menuRef: Object, close: () => void, toggle: () => void}}
 */
export function useLauncherPopover({ onClose, openDirect } = {}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  const close = () => { setOpen(false); onClose?.(); };

  const toggle = () => {
    if (open) { close(); return; }
    // Nothing to pick: act directly instead of opening an empty menu.
    if (openDirect) { openDirect(); return; }
    const at = launcherMenuPos(btnRef.current);
    if (!at) return;
    setPos(at);
    setOpen(true);
  };

  useLauncherDismiss(open, btnRef, menuRef, close);
  // The menu is portaled to document.body, so Tab alone would never reach it.
  useLauncherFocus(open, btnRef, menuRef, close);

  return { open, pos, btnRef, menuRef, close, toggle };
}

/** The launcher's opener button, with the caret that follows its open state. */
export function LauncherButton({ btnRef, open, ariaLabel, label, onToggle }) {
  return (
    <button
      ref={btnRef}
      type="button"
      className="compare-dueltrigger__btn compare-dueltrigger__btn--launcher"
      aria-haspopup="menu"
      aria-expanded={open}
      aria-label={ariaLabel}
      onClick={onToggle}
    >
      {label} {open ? '▾' : '▸'}
    </button>
  );
}

/** The menu itself, portaled to the body so no ancestor can clip it. */
export function LauncherMenu({ menuRef, pos, children }) {
  return createPortal(
    <span className="compare-dueltrigger__menu" role="menu" ref={menuRef} style={pos}>
      {children}
    </span>,
    document.body,
  );
}

/** A score shown beside a menu entry, tinted by its grade band. */
export function LauncherScore({ score }) {
  return (
    <span className={`compare-dueltrigger__itemScore ${scoreColorClass(score)}`}>
      {score1(score)}
    </span>
  );
}

/** The inline wrapper that keeps a launcher's clicks off the row behind it. */
export function LauncherRoot({ children }) {
  return (
    <span className="compare-dueltrigger" onClick={(e) => e.stopPropagation()}>
      {children}
    </span>
  );
}
