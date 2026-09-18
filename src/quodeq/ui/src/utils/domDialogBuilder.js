import { focusables, trapTab, restoreFocus } from './a11y.js';

// Distinct title/message ids per dialog for aria-labelledby / aria-describedby.
let dialogSeq = 0;

// True when the event started on one of the dialog's own action buttons. Such
// a button decides Enter through its own click, so the dialog-wide
// Enter-to-confirm must not fire on top of it: mount() focuses the first
// action and confirmDialog's danger variant focuses Cancel, so an
// unconditional shortcut would confirm the delete from a focused Cancel.
function onOwnButton(overlay, target) {
  return overlay.contains(target) && target.tagName === 'BUTTON';
}

/**
 * Shared DOM shell for confirmDialog.js and chooseDialog.js: the overlay +
 * dialog + title + message + actions row, the click-outside-to-cancel and
 * Escape-to-cancel wiring (plus an optional Enter-to-confirm, used only by
 * confirmDialog), and mount/unmount. Extracted verbatim from the
 * near-identical DOM-building code both dialogs used to duplicate.
 *
 * Accessibility (U-ACC-1, U-ACC-3): the overlay is named by its title and
 * described by its message, mount() moves focus to the first action and
 * keeps Tab inside the overlay, unmount() hands focus back to the opener.
 */
export function buildDialogShell({ title, message, dialogClassName, onCancel, onConfirm }) {
  dialogSeq += 1;
  const overlay = document.createElement('div');
  overlay.className = 'qd-confirm-overlay';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');

  const dialog = document.createElement('div');
  dialog.className = dialogClassName;

  const titleEl = document.createElement('h3');
  titleEl.className = 'qd-confirm-title';
  titleEl.id = `qd-confirm-title-${dialogSeq}`;
  titleEl.textContent = title;
  dialog.appendChild(titleEl);

  const messageEl = document.createElement('p');
  messageEl.className = 'qd-confirm-message';
  messageEl.id = `qd-confirm-message-${dialogSeq}`;
  messageEl.textContent = message;
  dialog.appendChild(messageEl);

  overlay.setAttribute('aria-labelledby', titleEl.id);
  overlay.setAttribute('aria-describedby', messageEl.id);

  const actionsEl = document.createElement('div');
  actionsEl.className = 'qd-confirm-actions';

  overlay.appendChild(dialog);

  let opener = null;

  function onKey(e) {
    if (e.key === 'Escape') onCancel();
    if (e.key === 'Enter' && onConfirm && !onOwnButton(overlay, e.target)) onConfirm();
    trapTab(overlay, e);
  }
  function onOverlayClick(e) {
    if (e.target === overlay) onCancel();
  }

  function mount() {
    opener = document.activeElement;
    dialog.appendChild(actionsEl);
    overlay.addEventListener('click', onOverlayClick);
    document.addEventListener('keydown', onKey);
    document.body.appendChild(overlay);
    const [first] = focusables(actionsEl);
    if (first) first.focus();
  }
  function unmount() {
    overlay.remove();
    document.removeEventListener('keydown', onKey);
    restoreFocus(opener);
  }

  return { overlay, dialog, titleEl, messageEl, actionsEl, mount, unmount };
}
