import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';

/**
 * Settings' "Restart terminal" workflow: kill the server shell via useApi(),
 * then signal the open terminal pane to clear its screen and reconnect (the
 * reconnect spawns a fresh PTY). Killing first also handles the case where
 * the terminal panel isn't currently open. Only dispatches on kill SUCCESS:
 * on failure the server keeps the live PTY and a reconnect would reattach to
 * the same shell — a fake restart — so the clear+reconnect is skipped and the
 * failure is logged instead.
 *
 * @returns {() => Promise<void>}
 */
export function useTerminalRestart() {
  const { killTerminal } = useApi();
  return async function restart() {
    const ok = await confirmDialog({
      title: t('settings.restartTerminalConfirmTitle'),
      message: t('settings.restartTerminalConfirmMessage'),
      variant: 'danger',
    });
    if (!ok) return;
    killTerminal()
      .then(() => window.dispatchEvent(new Event('quodeq:terminal-restart')))
      .catch((err) => { console.warn('Terminal restart: kill failed, not reconnecting', err); });
  };
}
