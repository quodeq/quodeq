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
    const overlay = document.createElement('div');
    overlay.className = 'qd-confirm-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.innerHTML = `
      <div class="qd-confirm-dialog qd-confirm-dialog--${variant}">
        <h3 class="qd-confirm-title"></h3>
        <p class="qd-confirm-message"></p>
        <div class="qd-confirm-actions">
          <button type="button" class="qd-confirm-btn qd-confirm-btn--cancel"></button>
          <button type="button" class="qd-confirm-btn qd-confirm-btn--confirm qd-confirm-btn--${variant}"></button>
        </div>
      </div>
    `;
    overlay.querySelector('.qd-confirm-title').textContent = title;
    overlay.querySelector('.qd-confirm-message').textContent = message;
    const cancelBtn = overlay.querySelector('.qd-confirm-btn--cancel');
    const confirmBtn = overlay.querySelector('.qd-confirm-btn--confirm');
    cancelBtn.textContent = cancelLabel;
    confirmBtn.textContent = confirmLabel;

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
