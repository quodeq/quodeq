import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useRef, useEffect } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { useApi } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

// Groups the section's own useState/useRef declarations so the outer
// component's body stays under the function-length cap; still called
// unconditionally at the top of the outer component, so hook-order is
// unaffected.
function useSharedRepoFields() {
  const [newUrl, setNewUrl] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);
  // Guards for synchronous dedup of save/disconnect calls
  const savingRef = useRef(false);
  const disconnectingRef = useRef(false);
  const initializedRef = useRef(false);
  return { newUrl, setNewUrl, confirming, setConfirming, error, setError, savingRef, disconnectingRef, initializedRef };
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

function buildConnectMutationConfig({ connectShared, setError, setNewUrl, refetchStatus, savingRef, queryClient }) {
  return {
    mutationFn: async (url) => {
      if (savingRef.current) return;
      savingRef.current = true;
      try {
        setError(null);
        const result = await connectShared(url);
        setNewUrl(result?.url || url);
        await refetchStatus();
        return result;
      } catch (err) {
        const errorMsg = apiErrorMessage(err, 'settings.connectFailed');
        setError(errorMsg);
        throw err;
      } finally {
        savingRef.current = false;
      }
    },
    onSuccess: () => {
      // Everything "shared"-prefixed, not just status: ProjectsPage's
      // useSharedProjects and usePublish read the SAME cache entries (audit
      // C6), so a connect made here must reach them too, not just this
      // section's own settings-detail status query (refetchStatus below
      // already covers that one specifically, for the inline UI).
      queryClient.invalidateQueries({ queryKey: sharedKeys.all() });
    },
  };
}

function buildDisconnectMutationConfig({ disconnectShared, setError, setNewUrl, setConfirming, refetchStatus, disconnectingRef, queryClient, onDisconnected }) {
  return {
    mutationFn: async () => {
      if (disconnectingRef.current) return;
      disconnectingRef.current = true;
      try {
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
      } catch (err) {
        const errorMsg = apiErrorMessage(err, 'settings.disconnectFailed');
        setError(errorMsg);
        throw err;
      } finally {
        disconnectingRef.current = false;
      }
    },
    onSuccess: () => {
      // Remove the list's cached data BEFORE invalidating: sharedKeys.status()
      // hasn't refetched/flipped `configured` to false anywhere yet at this
      // point, so an already-mounted list observer elsewhere (ProjectsPage's
      // useSharedProjects) is still enabled and would otherwise go on serving
      // its now-stale cached projects until its own status update lands --
      // removing first guarantees there is no shared-repo data left to render
      // in that window, and no leftover entry from a since-disconnected repo
      // to flash on a later reconnect to a different URL (ghost shared cards
      // after disconnect, final whole-branch review).
      queryClient.removeQueries({ queryKey: sharedKeys.list() });
      queryClient.invalidateQueries({ queryKey: sharedKeys.all() });
    },
  };
}

function buildStatusQueryConfig(getSharedStatus) {
  return {
    queryKey: [...sharedKeys.status(), 'settings-detail'],
    queryFn: () => getSharedStatus().catch(() => ({ configured: false, url: null })),
  };
}

function ErrorRow({ error }) {
  if (!error) return null;
  return (
    <div className="settings-row settings-row--last">
      <p className="inline-error">{error}</p>
    </div>
  );
}

function UrlStatusRow({ isLoading, status, configured, currentUrl }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label">{t('settings.repositoryUrl')}</span>
        <span className="settings-description">
          {isLoading && !status ? (
            t('settings.checkingEllipsis')
          ) : configured ? (
            <>{t('settings.configuredPrefix')} <code>{currentUrl}</code></>
          ) : (
            t('settings.notConfigured')
          )}
        </span>
      </div>
    </div>
  );
}

function UrlInputRow({ newUrl, setNewUrl, isSaving, isDisconnecting, handleSave }) {
  return (
    <div className="settings-row">
      <input
        type="text"
        className="settings-input"
        placeholder="https://github.com/team/results.git"
        value={newUrl}
        onChange={(e) => setNewUrl(e.target.value)}
        disabled={isSaving || isDisconnecting}
        aria-label={t('settings.sharedRepoUrlAria')}
      />
      <button
        type="button"
        className="settings-pill"
        onClick={handleSave}
        disabled={isSaving || isDisconnecting}
        aria-disabled={isSaving || isDisconnecting || undefined}
      >
        {isSaving ? t('settings.saving') : t('settings.save')}
      </button>
    </div>
  );
}

function DisconnectRow({ configured, confirming, setConfirming, isSaving, isDisconnecting, handleDisconnect }) {
  if (!configured) return null;
  if (!confirming) {
    return (
      <div className="settings-row settings-row--last">
        <button
          type="button"
          className="settings-pill settings-pill--accent"
          onClick={() => setConfirming(true)}
          disabled={isSaving || isDisconnecting}
          aria-disabled={isSaving || isDisconnecting || undefined}
        >
          {t('settings.disconnect')}
        </button>
      </div>
    );
  }
  return (
    <div className="settings-row settings-row--last">
      <span className="settings-row-confirm-label">{t('settings.disconnectConfirm')}</span>
      <button
        type="button"
        className="settings-pill settings-pill--confirm"
        onClick={handleDisconnect}
        disabled={isDisconnecting}
        aria-disabled={isDisconnecting || undefined}
      >
        {isDisconnecting ? t('settings.disconnecting') : t('settings.yes')}
      </button>
      <button
        type="button"
        className="settings-pill"
        onClick={() => setConfirming(false)}
        disabled={isDisconnecting}
        aria-disabled={isDisconnecting || undefined}
      >
        {t('settings.no')}
      </button>
    </div>
  );
}

export default function SharedRepoSection({ onDisconnected }) {
  const { getSharedStatus, connectShared, disconnectShared } = useApi();
  const queryClient = useQueryClient();

  const { newUrl, setNewUrl, confirming, setConfirming, error, setError, savingRef, disconnectingRef, initializedRef } = useSharedRepoFields();

  const { data: status, isLoading, refetch: refetchStatus } = useQuery(buildStatusQueryConfig(getSharedStatus));

  const configured = status?.configured ?? false;
  const currentUrl = status?.url ?? null;

  useInitNewUrl({ currentUrl, setNewUrl, initializedRef });

  const connectMutation = useMutation(buildConnectMutationConfig({ connectShared, setError, setNewUrl, refetchStatus, savingRef, queryClient }));

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

  const isSaving = connectMutation.isPending;
  const isDisconnecting = disconnectMutation.isPending;

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <span className="settings-label-row">
          <SectionLabel marker="▶">{t('settings.sharedRepoLabel')}</SectionLabel>
        </span>
      </div>

      <UrlStatusRow isLoading={isLoading} status={status} configured={configured} currentUrl={currentUrl} />
      <UrlInputRow newUrl={newUrl} setNewUrl={setNewUrl} isSaving={isSaving} isDisconnecting={isDisconnecting} handleSave={handleSave} />
      <ErrorRow error={error} />

      <DisconnectRow
        configured={configured} confirming={confirming} setConfirming={setConfirming}
        isSaving={isSaving} isDisconnecting={isDisconnecting} handleDisconnect={handleDisconnect}
      />
    </section>
  );
}
