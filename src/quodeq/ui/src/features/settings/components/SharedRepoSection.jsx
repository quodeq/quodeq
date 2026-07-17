import { useQuery, useMutation } from '@tanstack/react-query';
import { useState, useRef, useEffect } from 'react';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { useApi } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';

export default function SharedRepoSection() {
  const { getSharedStatus, connectShared, disconnectShared } = useApi();

  const [newUrl, setNewUrl] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);

  // Guards for synchronous dedup of save/disconnect calls
  const savingRef = useRef(false);
  const disconnectingRef = useRef(false);
  const initializedRef = useRef(false);

  const { data: status, isLoading, refetch: refetchStatus } = useQuery({
    queryKey: [...sharedKeys.status(), 'settings-detail'],
    queryFn: () => getSharedStatus().catch(() => ({ configured: false, url: null })),
  });

  const configured = status?.configured ?? false;
  const currentUrl = status?.url ?? null;

  // Initialize newUrl when currentUrl changes (only once per status update)
  useEffect(() => {
    if (currentUrl && !initializedRef.current) {
      setNewUrl(currentUrl);
      initializedRef.current = true;
    } else if (!currentUrl && initializedRef.current) {
      initializedRef.current = false;
    }
  }, [currentUrl]);

  const connectMutation = useMutation({
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
        const errorMsg = err?.message || 'failed to connect to repository';
        setError(errorMsg);
        throw err;
      } finally {
        savingRef.current = false;
      }
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: async () => {
      if (disconnectingRef.current) return;
      disconnectingRef.current = true;
      try {
        setError(null);
        await disconnectShared();
        setNewUrl('');
        setConfirming(false);
        await refetchStatus();
      } catch (err) {
        const errorMsg = err?.message || 'failed to disconnect from repository';
        setError(errorMsg);
        throw err;
      } finally {
        disconnectingRef.current = false;
      }
    },
  });

  const handleSave = () => {
    const trimmed = newUrl.trim();
    if (trimmed) {
      connectMutation.mutate(trimmed);
    }
  };

  const handleDisconnect = () => {
    disconnectMutation.mutate();
  };

  const isSaving = connectMutation.isPending;
  const isDisconnecting = disconnectMutation.isPending;

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <span className="settings-label-row">
          <SectionLabel marker="▶">shared repository</SectionLabel>
        </span>
      </div>

      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Repository URL</span>
          <span className="settings-description">
            {configured ? (
              <>Configured: <code>{currentUrl}</code></>
            ) : (
              <>Not configured</>
            )}
          </span>
        </div>
      </div>

      <div className="settings-row">
        <input
          type="text"
          className="settings-input"
          placeholder="https://github.com/team/results.git"
          value={newUrl}
          onChange={(e) => setNewUrl(e.target.value)}
          disabled={isSaving || isDisconnecting}
          aria-label="shared repository url"
        />
        <button
          type="button"
          className="settings-pill"
          onClick={handleSave}
          disabled={isSaving || isDisconnecting}
          aria-disabled={isSaving || isDisconnecting || undefined}
        >
          {isSaving ? 'saving...' : 'save'}
        </button>
      </div>

      {error && (
        <div className="settings-row settings-row--last">
          <p className="inline-error">{error}</p>
        </div>
      )}

      {configured && !confirming && (
        <div className="settings-row settings-row--last">
          <button
            type="button"
            className="settings-pill settings-pill--accent"
            onClick={() => setConfirming(true)}
            disabled={isSaving || isDisconnecting}
            aria-disabled={isSaving || isDisconnecting || undefined}
          >
            disconnect
          </button>
        </div>
      )}

      {configured && confirming && (
        <div className="settings-row settings-row--last">
          <span className="settings-row-confirm-label">disconnect?</span>
          <button
            type="button"
            className="settings-pill settings-pill--confirm"
            onClick={handleDisconnect}
            disabled={isDisconnecting}
            aria-disabled={isDisconnecting || undefined}
          >
            {isDisconnecting ? 'disconnecting...' : 'yes'}
          </button>
          <button
            type="button"
            className="settings-pill"
            onClick={() => setConfirming(false)}
            disabled={isDisconnecting}
            aria-disabled={isDisconnecting || undefined}
          >
            no
          </button>
        </div>
      )}
    </section>
  );
}
