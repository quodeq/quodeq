import { SYNC_ACTIVE_PHASES, SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { useCopyInvite } from '../hooks/useCopyInvite.js';
import { useSharedDisconnect } from '../hooks/useSharedDisconnect.js';
import { useDismissedConnectFailure } from '../hooks/useDismissedConnectFailure.js';
import SyncStrip from './SyncStrip.jsx';
import ConnectTeamCard from './ConnectTeamCard.jsx';

// The URL to retry: this screen's last attempt, else the one the failed slot
// carries (a connect started from the welcome's connect step or Settings,
// or before this page remounted).
function retryUrlFor(failedConnect, lastConnectUrl) {
  if (!failedConnect) return null;
  return lastConnectUrl ?? failedConnect.url ?? null;
}

// Whether the failure card shows, and what it carries. It shows for a live
// (not closed) failed connect only, configured or not: the connect starts
// from the welcome's connect step, which closes on the 202, so this card is
// where its failure comes back. While a retry runs the strip carries the
// progress and the card steps aside.
function useConnectCard(shared) {
  const connect = shared.status?.connect;
  const failedConnect = connect?.phase === SYNC_PHASE.ERROR ? connect : null;
  const { dismissed, dismiss } = useDismissedConnectFailure(failedConnect);
  const running = SYNC_ACTIVE_PHASES.has(connect?.phase);
  return {
    showCard: !running && Boolean(failedConnect) && !dismissed,
    retryUrl: retryUrlFor(failedConnect, shared.lastConnectUrl),
    onClose: dismiss,
  };
}

/**
 * The team results block under the Repositories header: the sync strip while
 * a repository is configured (or a first connect runs), and the failure card
 * when a connect failed (see pickStripState: a failed connect is reported by
 * the card only, so the strip keeps the working repository). The card's
 * field is prefilled with the URL that failed, so "connect" is the retry;
 * "close" dismisses that failure (by its finishedAt), and a later failure
 * shows again. Connecting and changing the repository open the welcome's
 * connect step (`onConnectEvaluations`). Everything reads `shared`
 * (useSharedProjects), the screen's one status poll.
 */
export function TeamResultsArea({ shared, onConnectEvaluations, onSharedDisconnected }) {
  const { invite, copyInvite } = useCopyInvite();
  const { disconnect, disconnecting } = useSharedDisconnect({ onDisconnected: onSharedDisconnected });
  const card = useConnectCard(shared);
  return (
    <>
      <SyncStrip
        status={shared.status}
        offline={shared.offline}
        updateFailed={shared.updateFailed}
        loadFailed={Boolean(shared.error)}
        lastSynced={shared.lastSynced}
        projectsCount={shared.projects.length}
        warming={shared.warming}
        invite={invite}
        onUpdate={shared.refresh}
        onCopyInvite={copyInvite}
        onChange={onConnectEvaluations}
        onDisconnect={disconnect}
        disconnecting={disconnecting}
      />
      {card.showCard && (
        <ConnectTeamCard
          initialUrl={card.retryUrl}
          onConnect={shared.connect}
          connecting={shared.connecting}
          error={shared.connectError}
          onClose={card.onClose}
          accessFailure={shared.accessFailure}
        />
      )}
    </>
  );
}
