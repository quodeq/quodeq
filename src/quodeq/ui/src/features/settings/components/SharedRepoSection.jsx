import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useRef, useEffect } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { useApi } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';
import { isSlotActive } from '../../../api/syncStatus.js';
import { useSyncStatus } from '../../../hooks/useSyncStatus.js';
import { connectSlotError } from '../../../hooks/connectSlotError.js';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import AccessPanel from '../../github-access/components/AccessPanel.jsx';
import { accessFailureFrom } from '../../github-access/accessFailure.js';
import { runExclusive } from '../settingsHelpers.js';
import { ErrorRow, UrlRow, UrlInputRow, DisconnectConfirmRow } from './sharedRepoRows.jsx';
import SharedSnippetsRow from './SharedSnippetsRow.jsx';

// Groups the section's own useState/useRef declarations so the outer
// component's body stays under the function-length cap; still called
// unconditionally at the top of the outer component, so hook-order is
// unaffected.
function useSharedRepoFields() {
  const [newUrl, setNewUrl] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState(null);
  const [accessFailure, setAccessFailure] = useState(null);
  // Guards for synchronous dedup of save/disconnect calls
  const savingRef = useRef(false);
  const disconnectingRef = useRef(false);
  const initializedRef = useRef(false);
  return { newUrl, setNewUrl, confirming, setConfirming, editing, setEditing, error, setError, accessFailure, setAccessFailure, savingRef, disconnectingRef, initializedRef };
}

// Initialize newUrl when currentUrl changes (only once per status update)
function useInitNewUrl({ currentUrl, setNewUrl, initializedRef }) {
  useEffect(() => {
    if (currentUrl && !initializedRef.current) {
      setNewUrl(currentUrl);
      initializedRef.current = true;
    } else if (!currentUrl && initializedRef.current) {
      initializedRef.current = false;
    }
  }, [currentUrl]);
}

function buildConnectMutationConfig({ connectShared, setError, setAccessFailure, setNewUrl, setEditing, refetchStatus, savingRef, queryClient }) {
  return {
    mutationFn: (url) => runExclusive(savingRef, async () => {
      setError(null);
      setAccessFailure(null);
      const result = await connectShared(url);
      setNewUrl(result?.url || url);
      setEditing(false);
      await refetchStatus();
      return result;
    }, (err) => {
      const failure = accessFailureFrom(err);
      if (failure) {
        setAccessFailure(failure);
        return;
      }
      setError(apiErrorMessage(err, 'settings.connectFailed'));
    }),
    onSuccess: () => {
      // Everything "shared"-prefixed, not just status: ProjectsPage's
      // useSharedProjects and usePublish read the SAME cache entries (audit
      // C6), so a connect made here must reach them too, not just the
      // status this section reads (refetchStatus in the mutation already
      // covers that one specifically, for the inline UI).
      queryClient.invalidateQueries({ queryKey: sharedKeys.all() });
    },
  };
}

function buildDisconnectMutationConfig({ disconnectShared, setError, setNewUrl, setConfirming, refetchStatus, disconnectingRef, queryClient, onDisconnected }) {
  return {
    mutationFn: () => runExclusive(disconnectingRef, async () => {
      setError(null);
      await disconnectShared();
      setNewUrl('');
      setConfirming(false);
      await refetchStatus();
      // A currently-'shared' project selection has nowhere left to
      // resolve once the repo is disconnected -- let the app reset it
      // (back to a local project, or no selection) rather than stranding
      // the user on a broken view.
      onDisconnected?.();
    }, (err) => setError(apiErrorMessage(err, 'settings.disconnectFailed'))),
    onSuccess: () => {
      // Remove the list's cached data BEFORE invalidating: sharedKeys.status()
      // hasn't refetched/flipped `configured` to false anywhere yet at this
      // point, so an already-mounted list observer elsewhere (ProjectsPage's
      // useSharedProjects) is still enabled and would otherwise go on serving
      // its now-stale cached projects until its own status update lands --
      // removing first guarantees there is no shared-repo data left to render
      // in that window, and no leftover entry from a since-disconnected repo
      // to flash on a later reconnect to a different URL (ghost shared cards
      // after disconnect).
      queryClient.removeQueries({ queryKey: sharedKeys.list() });
      queryClient.invalidateQueries({ queryKey: sharedKeys.all() });
    },
  };
}

// A server 500 and "genuinely not configured" must not collapse into the same
// silent not-configured state with no trace: log the real failure so a backend
// outage is debuggable, even though the UI still shows the not-configured
// empty state either way.
function useLogStatusFailure(error) {
  useEffect(() => {
    if (error) console.error('Failed to fetch shared repo status:', error);
  }, [error]);
}

// The rows under the header: the URL row, the field while connecting or
// changing, the access panel or error, and the disconnect confirmation.
function SharedRepoRows({ fields, sync, isSaving, isDisconnecting, handleSave, handleDisconnect }) {
  const { newUrl, setNewUrl, confirming, setConfirming, editing, setEditing, error, accessFailure, setAccessFailure } = fields;
  const { status, isLoading, configured, url: currentUrl } = sync;
  const refreshing = isSlotActive(sync.refresh);
  const cancelEdit = () => { setEditing(false); setNewUrl(currentUrl || ''); setAccessFailure(null); };
  return (
    <>
      <UrlRow
        isLoading={isLoading} status={status} configured={configured} currentUrl={currentUrl}
        busy={isSaving || isDisconnecting || confirming || refreshing}
        onChange={() => setEditing(true)}
        onDisconnect={editing ? null : () => setConfirming(true)}
      />
      <SharedSnippetsRow status={status} hidden={!configured || editing} />
      {(!configured || editing) && (
        <UrlInputRow
          newUrl={newUrl} setNewUrl={setNewUrl} isSaving={isSaving} isDisconnecting={isDisconnecting} handleSave={handleSave}
          onCancel={editing ? cancelEdit : null}
        />
      )}
      {accessFailure ? (
        <div className="settings-row settings-row--last">
          <AccessPanel failure={accessFailure} url={newUrl.trim()} onResolved={handleSave} onRetry={handleSave} />
        </div>
      ) : (
        <ErrorRow error={error ?? connectSlotError(sync.connect, 'settings.connectFailed')} />
      )}
      {configured && confirming && (
        <DisconnectConfirmRow
          blocked={isSaving || refreshing || isDisconnecting}
          isDisconnecting={isDisconnecting}
          onConfirm={handleDisconnect}
          onCancel={() => setConfirming(false)}
        />
      )}
    </>
  );
}

export default function SharedRepoSection({ onDisconnected }) {
  const { connectShared, disconnectShared } = useApi();
  const queryClient = useQueryClient();

  const fields = useSharedRepoFields();
  const { newUrl, setNewUrl, setConfirming, setEditing, setError, setAccessFailure, savingRef, disconnectingRef, initializedRef } = fields;

  const sync = useSyncStatus();
  const { refetch: refetchStatus, url: currentUrl } = sync;
  useLogStatusFailure(sync.error);

  useInitNewUrl({ currentUrl, setNewUrl, initializedRef });

  const connectMutation = useMutation(buildConnectMutationConfig({ connectShared, setError, setAccessFailure, setNewUrl, setEditing, refetchStatus, savingRef, queryClient }));

  const disconnectMutation = useMutation(buildDisconnectMutationConfig({
    disconnectShared, setError, setNewUrl, setConfirming, refetchStatus, disconnectingRef, queryClient, onDisconnected,
  }));

  const handleSave = () => {
    const trimmed = newUrl.trim();
    if (trimmed) {
      connectMutation.mutate(trimmed);
    }
  };

  const handleDisconnect = () => disconnectMutation.mutate();

  const isSaving = connectMutation.isPending || isSlotActive(sync.connect);
  const isDisconnecting = disconnectMutation.isPending;

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <span className="settings-label-row">
          <SectionLabel marker="▶">{t('settings.sharedRepoLabel')}</SectionLabel>
        </span>
      </div>

      <SharedRepoRows
        fields={fields} sync={sync} isSaving={isSaving} isDisconnecting={isDisconnecting}
        handleSave={handleSave} handleDisconnect={handleDisconnect}
      />
    </section>
  );
}
