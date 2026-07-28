import { SectionLabel } from '../../../components/terminal/index.js';

// Suspense fallback for the lazy-loaded RunHistoryPanel. Rides the same
// `.run-history-panel` / `.recharts-responsive-container` selectors the real
// panel does (dashboard.css / terminal.css) so the flex row's height math is
// identical before and after the chunk lands — no new dimensions here.
export default function RunHistoryPanelPlaceholder() {
  return (
    <section
      className="run-history-panel run-history-panel--terminal panel"
      aria-hidden="true"
      data-testid="run-history-panel-placeholder"
    >
      <div className="run-history-panel__header">
        <SectionLabel>score_history</SectionLabel>
      </div>
      <div className="recharts-responsive-container" />
    </section>
  );
}
