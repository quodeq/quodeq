/**
 * DOM-based confirmation dialog. Returns a Promise that resolves to true
 * (confirm) or false (cancel / clicked-outside). We roll our own instead of
 * using window.confirm because pywebview in frameless mode can suppress
 * native dialogs, leaving callers no feedback path.
 *
 * Usage:
 *   const ok = await confirmDialog({ title: 'Delete run?', message: '...' });
 *   if (!ok) return;
 */
const _ALLOWED_VARIANTS = new Set(['default', 'danger']);

export function confirmDialog({
  title = 'Confirm',
  message = 'Are you sure?',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default', // 'default' | 'danger'
} = {}) {
  return new Promise((resolve) => {
    if (typeof document === 'undefined') {
      resolve(false);
      return;
    }
    const safeVariant = _ALLOWED_VARIANTS.has(variant) ? variant : 'default';
    const overlay = document.createElement('div');
    overlay.className = 'qd-confirm-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');

    const dialog = document.createElement('div');
    dialog.className = `qd-confirm-dialog qd-confirm-dialog--${safeVariant}`;

    const titleEl = document.createElement('h3');
    titleEl.className = 'qd-confirm-title';
    titleEl.textContent = title;

    const messageEl = document.createElement('p');
    messageEl.className = 'qd-confirm-message';
    messageEl.textContent = message;

    const actions = document.createElement('div');
    actions.className = 'qd-confirm-actions';

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'qd-confirm-btn qd-confirm-btn--cancel';
    cancelBtn.textContent = cancelLabel;

    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.className = `qd-confirm-btn qd-confirm-btn--confirm qd-confirm-btn--${safeVariant}`;
    confirmBtn.textContent = confirmLabel;

    actions.appendChild(cancelBtn);
    actions.appendChild(confirmBtn);
    dialog.appendChild(titleEl);
    dialog.appendChild(messageEl);
    dialog.appendChild(actions);
    overlay.appendChild(dialog);

    function close(result) {
      overlay.remove();
      document.removeEventListener('keydown', onKey);
      resolve(result);
    }
    function onKey(e) {
      if (e.key === 'Escape') close(false);
      if (e.key === 'Enter') close(true);
    }
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });
    cancelBtn.addEventListener('click', () => close(false));
    confirmBtn.addEventListener('click', () => close(true));
    document.addEventListener('keydown', onKey);
    document.body.appendChild(overlay);
    confirmBtn.focus();
  });
}
