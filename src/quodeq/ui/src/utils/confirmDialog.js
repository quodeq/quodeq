/**
 * DOM-based confirmation dialog. We roll our own instead of using
 * window.confirm because pywebview in frameless mode can suppress
 * native dialogs, leaving callers no feedback path.
 *
 * Without `checkboxLabel` it resolves to a boolean (cancel/confirm).
 * With `checkboxLabel` it resolves to `{ ok, checked }` so the caller
 * can read both the user's confirmation and an opt-in side-effect.
 *
 * Usage:
 *   const ok = await confirmDialog({ title: 'Delete run?', message: '...' });
 *   if (!ok) return;
 *
 *   const { ok, checked } = await confirmDialog({
 *     title: 'Cancel evaluation?', checkboxLabel: 'Discard collected findings',
 *   });
 */
import { t } from '../strings/index.js';
import { buildDialogShell } from './domDialogBuilder.js';
const _ALLOWED_VARIANTS = new Set(['default', 'danger']);

export function confirmDialog({
  title = t('common.confirm'),
  message = t('common.areYouSure'),
  confirmLabel = t('common.confirm'),
  cancelLabel = t('common.cancel'),
  variant = 'default', // 'default' | 'danger'
  checkboxLabel = null,
  checkboxHint = '',
  checkboxDefault = false,
} = {}) {
  return new Promise((resolve) => {
    if (typeof document === 'undefined') {
      resolve(false);
      return;
    }
    const safeVariant = _ALLOWED_VARIANTS.has(variant) ? variant : 'default';

    function close(ok) {
      shell.unmount();
      if (checkboxInput) {
        resolve({ ok, checked: ok ? checkboxInput.checked : false });
      } else {
        resolve(ok);
      }
    }

    const shell = buildDialogShell({
      title, message,
      dialogClassName: `qd-confirm-dialog qd-confirm-dialog--${safeVariant}`,
      onCancel: () => close(false),
      onConfirm: () => close(true),
    });
    const { dialog, actionsEl } = shell;

    let checkboxInput = null;
    if (checkboxLabel) {
      const wrap = document.createElement('label');
      wrap.className = 'qd-confirm-checkbox';
      checkboxInput = document.createElement('input');
      checkboxInput.type = 'checkbox';
      checkboxInput.checked = !!checkboxDefault;
      const labelText = document.createElement('span');
      labelText.className = 'qd-confirm-checkbox-label';
      labelText.textContent = checkboxLabel;
      wrap.appendChild(checkboxInput);
      wrap.appendChild(labelText);
      if (checkboxHint) {
        const hint = document.createElement('span');
        hint.className = 'qd-confirm-checkbox-hint';
        hint.textContent = checkboxHint;
        wrap.appendChild(hint);
      }
      dialog.appendChild(wrap);
    }

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'qd-confirm-btn qd-confirm-btn--cancel';
    cancelBtn.textContent = cancelLabel;

    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.className = `qd-confirm-btn qd-confirm-btn--confirm qd-confirm-btn--${safeVariant}`;
    confirmBtn.textContent = confirmLabel;

    actionsEl.appendChild(cancelBtn);
    actionsEl.appendChild(confirmBtn);

    cancelBtn.addEventListener('click', () => close(false));
    confirmBtn.addEventListener('click', () => close(true));
    shell.mount();
    confirmBtn.focus();
  });
}
