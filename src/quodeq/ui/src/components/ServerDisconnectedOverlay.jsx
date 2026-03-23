import { getHealth } from '../api/index.js';

export default function ServerDisconnectedOverlay({ onReconnect }) {
  return (
    <div className="server-disconnected-overlay">
      <div className="server-disconnected-card">
        <div className="server-disconnected-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="1" y1="1" x2="23" y2="23" />
            <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55" />
            <path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39" />
            <path d="M10.71 5.05A16 16 0 0 1 22.56 9" />
            <path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88" />
            <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
            <line x1="12" y1="20" x2="12.01" y2="20" />
          </svg>
        </div>
        <h2>Server disconnected</h2>
        <p>The Quodeq server is not running. Start it from the menu bar icon or run:</p>
        <code>quodeq dashboard</code>
        <button type="button" className="server-retry-btn" onClick={() => getHealth().then(() => onReconnect()).catch((err) => console.warn('Reconnect failed:', err))}>
          Retry connection
        </button>
      </div>
    </div>
  );
}
