import ConsoleButton from './ConsoleButton.jsx';

const STATUS_LABEL = {
  online: 'Running',
  offline: 'Connection lost',
};

export default function ServerStatusPill({
  status,
  address,
  offlineMessage,
  onToggleConsole,
  consoleOpen = false,
  showDot = false,
}) {
  const isOnline = status === 'online';
  const showConsole = isOnline && typeof onToggleConsole === 'function';
  const statusClass = isOnline ? 'server-status--online' : 'server-status--offline';
  const dotClass = isOnline ? 'server-dot--online' : 'server-dot--offline';
  return (
    <div className="server-status-pill">
      <div className={`server-status-pill__status ${statusClass}`}>
        <span className={`server-dot ${dotClass}`} />
        {!isOnline && offlineMessage
          ? offlineMessage
          : <span>{STATUS_LABEL[isOnline ? 'online' : 'offline']}</span>}
        {isOnline && address && (
          <span className="server-address">{address}</span>
        )}
      </div>
      {showConsole && (
        <>
          <div className="server-status-pill__divider" aria-hidden="true" />
          <ConsoleButton open={consoleOpen} onToggle={onToggleConsole} showDot={showDot} />
        </>
      )}
    </div>
  );
}
