/**
 * DOM-based multi-action dialog. Mirrors confirmDialog but resolves to one
 * of N action keys (or null on cancel) instead of a boolean.
 *
 * Usage:
 *   const choice = await chooseDialog({
 *     title: 'Project already exists',
 *     message: '…',
 *     actions: [
 *       { key: 'replace', label: 'Replace', variant: 'danger' },
 *       { key: 'copy', label: 'Import as copy', variant: 'primary' },
 *     ],
 *   });
 *   if (choice === null) return; // user cancelled
 */
import { t } from '../strings/index.js';
import { buildDialogShell } from './domDialogBuilder.js';
const _ALLOWED_VARIANTS = new Set(['default', 'primary', 'danger']);

export function chooseDialog({
  title = t('common.chooseAnOption'),
  message = '',
  actions = [],
  cancelLabel = t('common.cancel'),
} = {}) {
  return new Promise((resolve) => {
    if (typeof document === 'undefined' || !Array.isArray(actions) || actions.length === 0) {
      resolve(null);
      return;
    }

    function close(value) {
      shell.unmount();
      resolve(value);
    }

    const shell = buildDialogShell({
      title, message,
      dialogClassName: 'qd-confirm-dialog qd-confirm-dialog--default',
      onCancel: () => close(null),
    });
    const { actionsEl } = shell;

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'qd-confirm-btn qd-confirm-btn--cancel';
    cancelBtn.textContent = cancelLabel;
    actionsEl.appendChild(cancelBtn);

    const buttons = actions.map((a) => {
      const variant = _ALLOWED_VARIANTS.has(a.variant) ? a.variant : 'default';
      const btn = document.createElement('button');
      btn.type = 'button';
      // 'default' is a neutral outline button (no --confirm). 'primary' is
      // the accent-filled affirmative action. 'danger' is the destructive
      // emphasized action. This keeps destructive vs safe visually distinct
      // even on themes where --color-accent and --color-danger are similar.
      const cls = variant === 'default'
        ? 'qd-confirm-btn'
        : `qd-confirm-btn qd-confirm-btn--confirm qd-confirm-btn--${variant}`;
      btn.className = cls;
      btn.textContent = a.label;
      actionsEl.appendChild(btn);
      return { btn, key: a.key };
    });

    cancelBtn.addEventListener('click', () => close(null));
    for (const { btn, key } of buttons) {
      btn.addEventListener('click', () => close(key));
    }
    shell.mount();
    // Default focus: when any action is destructive, focus Cancel so Enter
    // cannot accidentally fire the destructive button. Otherwise focus the
    // last (rightmost / primary) action.
    const hasDanger = actions.some((a) => a.variant === 'danger');
    if (hasDanger || buttons.length === 0) cancelBtn.focus();
    else buttons[buttons.length - 1].btn.focus();
  });
}
