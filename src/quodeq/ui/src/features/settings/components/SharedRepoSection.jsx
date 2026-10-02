import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useRef, useEffect } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { useApi } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';
import { isSlotActive } from '../../../api/syncStatus.js';
import { useSyncStatus } from '../../../hooks/useSyncStatus.js';
import { connectSlotError } from '../../../hooks/connectSlotError.js';
import { t } from '../../../strings/index.js';
import { apiErrorMessage, isAccessCode } from '../../../strings/apiErrors.js';
import { SettingsRowLabel } from './settingsRowParts.jsx';
import AccessPanel from '../../github-access/components/AccessPanel.jsx';
import { runExclusive } from '../settingsHelpers.js';

// Groups the section's own useState/useRef declarations so the outer
// component's body stays under the function-length cap; still called
// unconditionally at the top of the outer component, so hook-order is
// unaffected.
function useSharedRepoFields() {
  const [newUrl, setNewUrl] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);
  const [accessFailure, setAccessFailure] = useState(null);
  // Guards for synchronous dedup of save/disconnect calls
  const savingRef = useRef(false);
  const disconnectingRef = useRef(false);
  const initializedRef = useRef(false);
  return { newUrl, setNewUrl, confirming, setConfirming, error, setError, accessFailure, setAccessFailure, savingRef, disconnectingRef, initializedRef };
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

function buildConnectMutationConfig({ connectShared, setError, setAccessFailure, setNewUrl, refetchStatus, savingRef, queryClient }) {
  return {
    mutationFn: (url) => runExclusive(savingRef, async () => {
      setError(null);
      setAccessFailure(null);
      const result = await connectShared(url);
      setNewUrl(result?.url || url);
      await refetchStatus();
      return result;
    }, (err) => {
      if (isAccessCode(err?.code)) {
        setAccessFailure({ kind: err.body?.kind, detail: err.body?.detail || '', host: err.body?.host || '', isGitHub: Boolean(err.body?.isGitHub), cloneUrl: err.body?.cloneUrl || '' });
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
      <SettingsRowLabel
        hintSlot={false}
        label={t('settings.repositoryUrl')}
        description={isLoading && !status ? (
          t('settings.checkingEllipsis')
        ) : configured ? (
          <>{t('settings.configuredPrefix')} <code>{currentUrl}</code></>
        ) : (
          t('settings.notConfigured')
        )}
      />
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
  const { connectShared, disconnectShared } = useApi();
  const queryClient = useQueryClient();

  const { newUrl, setNewUrl, confirming, setConfirming, error, setError, accessFailure, setAccessFailure, savingRef, disconnectingRef, initializedRef } = useSharedRepoFields();

  const sync = useSyncStatus();
  const { status, isLoading, refetch: refetchStatus, configured, url: currentUrl } = sync;
  useLogStatusFailure(sync.error);

  useInitNewUrl({ currentUrl, setNewUrl, initializedRef });

  const connectMutation = useMutation(buildConnectMutationConfig({ connectShared, setError, setAccessFailure, setNewUrl, refetchStatus, savingRef, queryClient }));

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

      <UrlStatusRow isLoading={isLoading} status={status} configured={configured} currentUrl={currentUrl} />
      <UrlInputRow newUrl={newUrl} setNewUrl={setNewUrl} isSaving={isSaving} isDisconnecting={isDisconnecting} handleSave={handleSave} />
      {accessFailure ? (
        <div className="settings-row settings-row--last">
          <AccessPanel failure={accessFailure} url={newUrl.trim()} onResolved={handleSave} onRetry={handleSave} />
        </div>
      ) : (
        <ErrorRow error={error ?? connectSlotError(sync.connect, 'settings.connectFailed')} />
      )}

      <DisconnectRow
        configured={configured} confirming={confirming} setConfirming={setConfirming}
        isSaving={isSaving} isDisconnecting={isDisconnecting} handleDisconnect={handleDisconnect}
      />
    </section>
  );
}
