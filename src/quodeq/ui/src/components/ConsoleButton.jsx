const CONSOLE_ICON = (
  <svg className="console-button__icon" viewBox="0 0 16 16" fill="none"
       stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
       aria-hidden="true">
    <rect x="1" y="2" width="14" height="12" rx="2" />
    <polyline points="4.5,6.5 7,9 4.5,11.5" />
    <line x1="9" y1="11" x2="12" y2="11" />
  </svg>
);

/**
 * Toggle button for opening/closing a "Console" side-pane log window.
 * Used everywhere we surface a streaming-log viewer (evaluation cards,
 * dashboard server, Ollama). No open-state highlight — visual stays the
 * same; the dynamic aria-label is what conveys state to assistive tech.
 *
 * @param {{ open: boolean, onToggle: () => void, showDot?: boolean }} props
 *   `showDot` renders a small accent dot in the corner — used by the
 *   evaluation card to nudge first-time users.
 */
export default function ConsoleButton({ open, onToggle, showDot = false }) {
  const label = open ? 'Hide console' : 'Show console';
  return (
    <button
      type="button"
      className="console-button"
      onClick={(e) => { e.stopPropagation(); onToggle(); }}
      aria-label={label}
      aria-expanded={open}
      title={label}
    >
      {CONSOLE_ICON}
      <span className="console-button__label">Console</span>
      {showDot && <span className="console-button__dot" aria-hidden="true" />}
    </button>
  );
}
