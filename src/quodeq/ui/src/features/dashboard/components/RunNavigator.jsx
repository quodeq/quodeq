// Props: { currentRun, isLatest, isOldest, actions: { onPrev, onNext, onLatest, onView, onPrevHover, onNextHover, onLatestHover } }
// Prev/next/latest navigation buttons + current run display + optional "View run" button.
// Hover handlers (onPrevHover, etc.) are optional — when wired they prefetch the
// adjacent run's dashboard so the click feels instant.

export default function RunNavigator({
  currentRun, isLatest, isOldest,
  actions: { onPrev, onNext, onLatest, onView, onPrevHover, onNextHover, onLatestHover } = {},
}) {
  return (
    <div className="run-navigator">
      <button
        type="button"
        className="run-nav-action run-nav-action--primary"
        onClick={onLatest}
        onMouseEnter={onLatestHover}
        onFocus={onLatestHover}
        disabled={isLatest}
        title="Go to latest run"
      >
        Latest
      </button>

      <div className="run-nav-pager">
        <button
          type="button"
          className="run-nav-btn"
          onClick={onPrev}
          onMouseEnter={onPrevHover}
          onFocus={onPrevHover}
          disabled={isOldest}
          aria-label="Older evaluation"
          title="Older evaluation"
        >
          ‹
        </button>
        <span className="run-nav-label">{currentRun}</span>
        <button
          type="button"
          className="run-nav-btn"
          onClick={onNext}
          onMouseEnter={onNextHover}
          onFocus={onNextHover}
          disabled={isLatest}
          aria-label="Newer evaluation"
          title="Newer evaluation"
        >
          ›
        </button>
      </div>

      {onView && (
        <button
          type="button"
          className="run-nav-action run-nav-action--outline"
          onClick={onView}
          title="Open this run"
        >
          View →
        </button>
      )}
    </div>
  );
}
