import { useEffect } from 'react';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { useCopyInvite } from '../hooks/useCopyInvite.js';
import { useSharedDisconnect } from '../hooks/useSharedDisconnect.js';
import SyncStrip from './SyncStrip.jsx';
import ConnectTeamCard from './ConnectTeamCard.jsx';

// A connect that reaches DONE has configured the repository: the card has
// done its job and closes (the strip takes over).
function useCloseOnConnected(connect, onConnectOpenChange) {
  const phase = connect?.phase;
  const finishedAt = connect?.finishedAt;
  useEffect(() => {
    if (phase === SYNC_PHASE.DONE) onConnectOpenChange(false);
  }, [phase, finishedAt, onConnectOpenChange]);
}

/**
 * The team results block under the Repositories header: the sync strip while
 * a repository is configured (or a first connect runs), and the connect card
 * when the header's "connect team results" or the strip's "change
 * repository" opened it, or always on an empty page with nothing connected.
 * A failed connect is reported by the card only (see pickStripState): with
 * nothing configured the card opens on its own so the error is never hidden,
 * its field prefilled with the URL that failed, so "connect" is the retry.
 * Everything reads `shared` (useSharedProjects), the screen's one status poll.
 */
export function TeamResultsArea({ shared, connectOpen, onConnectOpenChange, emptyPage, onSharedDisconnected }) {
  const { invite, copyInvite } = useCopyInvite();
  const disconnect = useSharedDisconnect({ onDisconnected: onSharedDisconnected });
  useCloseOnConnected(shared.status?.connect, onConnectOpenChange);
  const failedConnect = shared.status?.connect?.phase === SYNC_PHASE.ERROR ? shared.status.connect : null;
  const showCard = connectOpen || (!shared.configured && (emptyPage || Boolean(failedConnect)));
  const { connect } = shared;
  // The URL to retry: this screen's last attempt, else the one the failed slot carries (a
  // connect started from Settings, or before this page remounted).
  const retryUrl = failedConnect ? (shared.lastConnectUrl ?? failedConnect.url ?? null) : null;
  return (
    <>
      <SyncStrip
        status={shared.status}
        offline={shared.offline}
        updateFailed={shared.updateFailed}
        loadFailed={Boolean(shared.error)}
        lastSynced={shared.lastSynced}
        projectsCount={shared.projects.length}
        invite={invite}
        onUpdate={shared.refresh}
        onCopyInvite={copyInvite}
        onChange={() => onConnectOpenChange(true)}
        onDisconnect={disconnect}
      />
      {showCard && (
        <ConnectTeamCard
          initialUrl={retryUrl}
          onConnect={connect}
          connecting={shared.connecting}
          error={shared.connectError}
          accessFailure={shared.accessFailure}
        />
      )}
    </>
  );
}
