import { SectionLabel } from '../../../components/terminal/index.js';

// Suspense fallback for the lazy-loaded RunHistoryPanel. Rides the same
// `.run-history-panel` selectors the real panel does (dashboard.css /
// terminal.css) so the flex row's height math is identical before and after
// the chunk lands — no new dimensions here. `run-history-panel__chart-slot`
// is a local class added alongside `.recharts-responsive-container` in the
// dashboard.css flex:1/min-height:160px rule, so this div doesn't have to
// impersonate a recharts-internal class name to pick up the sizing.
export default function RunHistoryPanelPlaceholder() {
  return (
    <section
      className="run-history-panel run-history-panel--terminal panel"
      aria-hidden="true"
      data-testid="run-history-panel-placeholder"
    >
      <div className="run-history-panel__header">
        {/* Deliberately omits the real header's controls/stats — both are
            single-line flex rows, so leaving them out doesn't change height. */}
        <SectionLabel>score_history</SectionLabel>
      </div>
      <div className="run-history-panel__chart-slot" />
    </section>
  );
}
