import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { t } from '../../../strings/index.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';
import { DIALOG_VARIANT } from '../../../vocab/dialogVariant.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';

/**
 * The sync strip's "disconnect": confirms, deletes the team repository's
 * local clone (DELETE /shared/config), then drops the cached team list
 * before re-reading everything shared, so no team card from the old
 * repository lingers while the status catches up (same order as
 * Settings' SharedRepoSection). `onDisconnected` lets the app move a team
 * project selection back to a local one.
 *
 * The server waits for the shared warm-up's project in flight before it
 * removes the clone, so a disconnect can take a while: `disconnecting` is
 * true meanwhile, and a second call does nothing until the first is done.
 * @param {{onDisconnected?: () => void}} options
 * @returns {{disconnect: () => Promise<void>, disconnecting: boolean}}
 */
export function useSharedDisconnect({ onDisconnected } = {}) {
  const { disconnectShared } = useApi();
  const queryClient = useQueryClient();
  const { showToast } = useSidePane();
  const [disconnecting, setDisconnecting] = useState(false);
  const inFlight = useRef(false);
  const remove = useCallback(async () => {
    try {
      await disconnectShared();
    } catch (err) {
      showToast(apiErrorMessage(err, 'sync.disconnectFailed'));
      return;
    }
    queryClient.removeQueries({ queryKey: sharedKeys.list() });
    await queryClient.invalidateQueries({ queryKey: sharedKeys.all() });
    onDisconnected?.();
  }, [disconnectShared, queryClient, showToast, onDisconnected]);
  const disconnect = useCallback(async () => {
    if (inFlight.current) return;
    const ok = await confirmDialog({
      title: t('sync.disconnectConfirmTitle'),
      message: t('sync.disconnectConfirmMsg'),
      confirmLabel: t('sync.disconnectConfirm'),
      cancelLabel: t('common.cancel'),
      variant: DIALOG_VARIANT.DANGER,
    });
    if (!ok || inFlight.current) return;
    inFlight.current = true;
    setDisconnecting(true);
    try {
      await remove();
    } finally {
      inFlight.current = false;
      setDisconnecting(false);
    }
  }, [remove]);
  return { disconnect, disconnecting };
}
