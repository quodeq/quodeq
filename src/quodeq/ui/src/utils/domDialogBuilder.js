/**
 * Shared DOM shell for confirmDialog.js and chooseDialog.js: the overlay +
 * dialog + title + message + actions row, the click-outside-to-cancel and
 * Escape-to-cancel wiring (plus an optional Enter-to-confirm, used only by
 * confirmDialog), and mount/unmount. Extracted verbatim from the
 * near-identical DOM-building code both dialogs used to duplicate.
 */
export function buildDialogShell({ title, message, dialogClassName, onCancel, onConfirm }) {
  const overlay = document.createElement('div');
  overlay.className = 'qd-confirm-overlay';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');

  const dialog = document.createElement('div');
  dialog.className = dialogClassName;

  const titleEl = document.createElement('h3');
  titleEl.className = 'qd-confirm-title';
  titleEl.textContent = title;
  dialog.appendChild(titleEl);

  const messageEl = document.createElement('p');
  messageEl.className = 'qd-confirm-message';
  messageEl.textContent = message;
  dialog.appendChild(messageEl);

  const actionsEl = document.createElement('div');
  actionsEl.className = 'qd-confirm-actions';

  overlay.appendChild(dialog);

  function onKey(e) {
    if (e.key === 'Escape') onCancel();
    if (e.key === 'Enter' && onConfirm) onConfirm();
  }
  function onOverlayClick(e) {
    if (e.target === overlay) onCancel();
  }

  function mount() {
    dialog.appendChild(actionsEl);
    overlay.addEventListener('click', onOverlayClick);
    document.addEventListener('keydown', onKey);
    document.body.appendChild(overlay);
  }
  function unmount() {
    overlay.remove();
    document.removeEventListener('keydown', onKey);
  }

  return { overlay, dialog, titleEl, messageEl, actionsEl, mount, unmount };
}
