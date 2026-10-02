import { useCallback } from 'react';
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
 * @param {{onDisconnected?: () => void}} options
 * @returns {() => Promise<void>}
 */
export function useSharedDisconnect({ onDisconnected } = {}) {
  const { disconnectShared } = useApi();
  const queryClient = useQueryClient();
  const { showToast } = useSidePane();
  return useCallback(async () => {
    const ok = await confirmDialog({
      title: t('sync.disconnectConfirmTitle'),
      message: t('sync.disconnectConfirmMsg'),
      confirmLabel: t('sync.disconnectConfirm'),
      cancelLabel: t('common.cancel'),
      variant: DIALOG_VARIANT.DANGER,
    });
    if (!ok) return;
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
}
