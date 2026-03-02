// Props: { currentRun, isLatest, isOldest, onPrev, onNext, onLatest, onView }
// Prev/next/latest navigation buttons + current run display + optional "View run" button
// currentRun: string (e.g. '20260228' or 'latest')

export default function RunNavigator({ currentRun, isLatest, isOldest, onPrev, onNext, onLatest, onView }) {
  return (
    <div className="run-navigator">
      <button
        type="button"
        className="run-nav-action run-nav-action--danger"
        onClick={onLatest}
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
          className="run-nav-action"
          onClick={onView}
          title="Open this run"
        >
          View run
        </button>
      )}
    </div>
  );
}
