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
import { buildDialogShell, BUTTON_TYPE } from './domDialogBuilder.js';
import { DIALOG_VARIANT } from '../vocab/dialogVariant.js';
const _ALLOWED_VARIANTS = new Set([DIALOG_VARIANT.DEFAULT, DIALOG_VARIANT.DANGER]);

function createCheckbox(dialog, { checkboxLabel, checkboxHint, checkboxDefault }) {
  if (!checkboxLabel) return null;
  const wrap = document.createElement('label');
  wrap.className = 'qd-confirm-checkbox';
  const checkboxInput = document.createElement('input');
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
  return checkboxInput;
}

function createConfirmButtons(actionsEl, { cancelLabel, confirmLabel, safeVariant }) {
  const cancelBtn = document.createElement(BUTTON_TYPE);
  cancelBtn.type = BUTTON_TYPE;
  cancelBtn.className = 'qd-confirm-btn qd-confirm-btn--cancel';
  cancelBtn.textContent = cancelLabel;

  const confirmBtn = document.createElement(BUTTON_TYPE);
  confirmBtn.type = BUTTON_TYPE;
  confirmBtn.className = `qd-confirm-btn qd-confirm-btn--confirm qd-confirm-btn--${safeVariant}`;
  confirmBtn.textContent = confirmLabel;

  actionsEl.appendChild(cancelBtn);
  actionsEl.appendChild(confirmBtn);
  return { cancelBtn, confirmBtn };
}

/**
 * Modal confirmation. Resolves false on cancel. With `checkboxLabel` set it
 * resolves to `{ confirmed, checked }` instead of a bare boolean, for the
 * "don't ask again"-style options.
 *
 * @returns {Promise<boolean|{confirmed: boolean, checked: boolean}>}
 */
export function confirmDialog({
  title = t('common.confirm'),
  message = t('common.areYouSure'),
  confirmLabel = t('common.confirm'),
  cancelLabel = t('common.cancel'),
  variant = DIALOG_VARIANT.DEFAULT, // 'default' | 'danger'
  checkboxLabel = null,
  checkboxHint = '',
  checkboxDefault = false,
} = {}) {
  return new Promise((resolve) => {
    if (typeof document === 'undefined') {
      resolve(false);
      return;
    }
    const safeVariant = _ALLOWED_VARIANTS.has(variant) ? variant : DIALOG_VARIANT.DEFAULT;

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

    const checkboxInput = createCheckbox(dialog, { checkboxLabel, checkboxHint, checkboxDefault });
    const { cancelBtn, confirmBtn } = createConfirmButtons(actionsEl, { cancelLabel, confirmLabel, safeVariant });

    cancelBtn.addEventListener('click', () => close(false));
    confirmBtn.addEventListener('click', () => close(true));
    shell.mount();
    (safeVariant === DIALOG_VARIANT.DANGER ? cancelBtn : confirmBtn).focus();
  });
}
