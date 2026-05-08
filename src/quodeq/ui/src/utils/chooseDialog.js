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
const _ALLOWED_VARIANTS = new Set(['default', 'primary', 'danger']);

export function chooseDialog({
  title = 'Choose an option',
  message = '',
  actions = [],
  cancelLabel = 'Cancel',
} = {}) {
  return new Promise((resolve) => {
    if (typeof document === 'undefined' || !Array.isArray(actions) || actions.length === 0) {
      resolve(null);
      return;
    }
    const overlay = document.createElement('div');
    overlay.className = 'qd-confirm-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');

    const dialog = document.createElement('div');
    dialog.className = 'qd-confirm-dialog qd-confirm-dialog--default';

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
    dialog.appendChild(actionsEl);
    overlay.appendChild(dialog);

    function close(value) {
      overlay.remove();
      document.removeEventListener('keydown', onKey);
      resolve(value);
    }
    function onKey(e) {
      if (e.key === 'Escape') close(null);
    }
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(null); });
    cancelBtn.addEventListener('click', () => close(null));
    for (const { btn, key } of buttons) {
      btn.addEventListener('click', () => close(key));
    }
    document.addEventListener('keydown', onKey);
    document.body.appendChild(overlay);
    // Default focus: when any action is destructive, focus Cancel so Enter
    // cannot accidentally fire the destructive button. Otherwise focus the
    // last (rightmost / primary) action.
    const hasDanger = actions.some((a) => a.variant === 'danger');
    if (hasDanger || buttons.length === 0) cancelBtn.focus();
    else buttons[buttons.length - 1].btn.focus();
  });
}
